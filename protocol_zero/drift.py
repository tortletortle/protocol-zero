"""Labelled-feedback drift monitors. Alerts never certify integrity or update calibration."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from math import log, sqrt, isfinite
from typing import Sequence

def _prob(x, name, opened=False):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x):
        raise ValueError(f"{name} must be finite")
    if opened and not 0 < x < 1: raise ValueError(f"{name} must be in (0,1)")
    if not opened and not 0 <= x <= 1: raise ValueError(f"{name} must be in [0,1]")

def _posint(x,name):
    if type(x) is not int or x < 1: raise ValueError(f"{name} must be a positive integer")

class LikelihoodCUSUM:
    """One-sided Bernoulli log-likelihood CUSUM for rising error probability."""
    def __init__(self, baseline_rate, target_increase=.15, threshold=9.0):
        _prob(baseline_rate,"baseline_rate",True); _prob(target_increase,"target_increase",True)
        if baseline_rate+target_increase >= 1: raise ValueError("target rate must be < 1")
        if isinstance(threshold,bool) or not isinstance(threshold,(int,float)) or not isfinite(threshold) or threshold<=0:
            raise ValueError("threshold must be positive and finite")
        self.target_rate=baseline_rate+target_increase; self.threshold=float(threshold)
        self._e=log(self.target_rate/baseline_rate)
        self._ok=log((1-self.target_rate)/(1-baseline_rate))
        self.statistic=0.0; self.alarm_at=None
    def update(self,error,index):
        if type(error) is not bool: raise ValueError("error must be boolean")
        _posint(index+1,"index+1")
        self.statistic=max(0.0,self.statistic+(self._e if error else self._ok))
        if self.alarm_at is None and self.statistic>=self.threshold: self.alarm_at=index
        return self.alarm_at is not None

class PageHinkleyIncrease:
    """One-sided Page-Hinkley mean-shift detector."""
    def __init__(self,baseline_rate,delta=.02,threshold=10.0):
        _prob(baseline_rate,"baseline_rate",True); _prob(delta,"delta",True)
        if isinstance(threshold,bool) or not isinstance(threshold,(int,float)) or not isfinite(threshold) or threshold<=0:
            raise ValueError("threshold must be positive and finite")
        self.mean=float(baseline_rate); self.delta=float(delta); self.threshold=float(threshold)
        self.n=0; self.cumulative=0.0; self.minimum=0.0; self.alarm_at=None
    def update(self,error,index):
        if type(error) is not bool: raise ValueError("error must be boolean")
        _posint(index+1,"index+1")
        self.n+=1; value=int(error); self.mean+=(value-self.mean)/self.n
        self.cumulative+=value-self.mean-self.delta
        self.minimum=min(self.minimum,self.cumulative)
        if self.alarm_at is None and self.cumulative-self.minimum>=self.threshold: self.alarm_at=index
        return self.alarm_at is not None

class HoeffdingWindowDetector:
    """ADWIN-inspired split-window baseline; not the ADWIN algorithm."""
    def __init__(self,min_window=64,max_window=2048,delta=.01,check_every=16):
        for x,n in ((min_window,"min_window"),(max_window,"max_window"),(check_every,"check_every")): _posint(x,n)
        if max_window<2*min_window: raise ValueError("max_window must be >= 2 * min_window")
        _prob(delta,"delta",True)
        self.min_window=min_window; self.max_window=max_window; self.delta=float(delta); self.check_every=check_every
        self.values=deque(maxlen=max_window); self.n=0; self.alarm_at=None
        self.cut=None; self.mean_difference=None; self.bound=None
    def update(self,error,index):
        if type(error) is not bool: raise ValueError("error must be boolean")
        _posint(index+1,"index+1")
        self.values.append(int(error)); self.n+=1
        if self.alarm_at is not None or len(self.values)<2*self.min_window or self.n%self.check_every: return self.alarm_at is not None
        vals=list(self.values); size=len(vals); prefix=[0]
        for v in vals: prefix.append(prefix[-1]+v)
        cuts=list(range(self.min_window,size-self.min_window+1,self.check_every))
        if not cuts: return False
        best=None; m=len(cuts)
        for cut in cuts:
            diff=(prefix[size]-prefix[cut])/(size-cut)-prefix[cut]/cut
            eps=sqrt(.5*log(2*m/self.delta)*(1/cut+1/(size-cut)))
            if diff>eps and (best is None or diff/eps>best[0]): best=(diff/eps,cut,diff,eps)
        if best: _,self.cut,self.mean_difference,self.bound=best; self.alarm_at=index
        return self.alarm_at is not None

@dataclass(frozen=True)
class MonitorConfig:
    min_feedback_per_class:int=64
    cusum_target_increase:float=.15
    cusum_threshold:float=9.0
    page_hinkley_delta:float=.02
    page_hinkley_threshold:float=10.0
    window_min:int=64
    window_max:int=2048
    window_delta:float=.01
    window_check_every:int=16
    def __post_init__(self):
        _posint(self.min_feedback_per_class,"min_feedback_per_class")
        _prob(self.cusum_target_increase,"cusum_target_increase",True)
        _prob(self.page_hinkley_delta,"page_hinkley_delta",True); _prob(self.window_delta,"window_delta",True)
        for x,n in ((self.cusum_threshold,"cusum_threshold"),(self.page_hinkley_threshold,"page_hinkley_threshold")):
            if isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or x<=0: raise ValueError(f"{n} must be positive")
        for x,n in ((self.window_min,"window_min"),(self.window_max,"window_max"),(self.window_check_every,"window_check_every")): _posint(x,n)
        if self.window_max<2*self.window_min: raise ValueError("window_max must be >= 2 * window_min")

def _profile_rate(profile,error_field,total_field):
    errors=getattr(profile,error_field); total=getattr(profile,total_field)
    _posint(total,total_field)
    if type(errors) is not int or not 0<=errors<=total: raise ValueError(f"invalid {error_field}")
    return (errors+.5)/(total+1.0)  # Jeffreys smoothing

def monitor_source(profile,feedback:Sequence[tuple[bool,bool]],*,evaluation_set_id,
                   evaluation_environment_id,config=MonitorConfig()):
    """Monitor FN and FP separately from labelled (ground_truth, source_verdict) rows."""
    for name,value in (("evaluation_set_id",evaluation_set_id),("evaluation_environment_id",evaluation_environment_id)):
        if not isinstance(value,str) or not value.strip(): raise ValueError(f"{name} must be non-empty")
    source=getattr(profile,"source_id",None); cal_id=getattr(profile,"calibration_set_id",None); env=getattr(profile,"environment_id",None)
    if not all(isinstance(x,str) and x.strip() for x in (source,cal_id,env)):
        raise ValueError("profile requires source_id, calibration_set_id and environment_id")
    if cal_id==evaluation_set_id: raise ValueError("calibration/evaluation data leakage")
    if env!=evaluation_environment_id:
        return dict(source_id=source,status="abstain",reason="environment_mismatch",classes={},
                    monitored_classes=[],unmonitored_classes=["valid_candidates","invalid_candidates"],
                    calibration_updated=False,integrity_verified=False)
    if not bool(getattr(profile,"calibrated",False)):
        return dict(source_id=source,status="abstain",reason="insufficient_calibration",classes={},
                    monitored_classes=[],unmonitored_classes=["valid_candidates","invalid_candidates"],
                    calibration_updated=False,integrity_verified=False)
    if not isinstance(feedback,Sequence): raise TypeError("feedback must be a sequence")
    errors={"valid_candidates":[],"invalid_candidates":[]}
    for row in feedback:
        if not isinstance(row,(tuple,list)) or len(row)!=2: raise ValueError("rows must be (truth, verdict)")
        truth,verdict=row
        if type(truth) is not bool or type(verdict) is not bool: raise ValueError("truth and verdict must be bool")
        errors["valid_candidates"].append(not verdict) if truth else errors["invalid_candidates"].append(verdict)
    params={"valid_candidates":("false_negative","positive_examples"),
            "invalid_candidates":("false_positive","negative_examples")}
    results={}
    for cls,series in errors.items():
        if len(series)<config.min_feedback_per_class:
            results[cls]=dict(status="insufficient_feedback",n=len(series),baseline_error_rate=None,detectors={})
            continue
        err_field,total_field=params[cls]; baseline=_profile_rate(profile,err_field,total_field)
        detectors={}; unavailable={}
        if baseline+config.cusum_target_increase<1:
            detectors["likelihood_cusum"]=LikelihoodCUSUM(baseline,config.cusum_target_increase,config.cusum_threshold)
        else: unavailable["likelihood_cusum"]="baseline_too_high_for_target_rate"
        detectors["page_hinkley"]=PageHinkleyIncrease(baseline,config.page_hinkley_delta,config.page_hinkley_threshold)
        detectors["hoeffding_window"]=HoeffdingWindowDetector(config.window_min,config.window_max,config.window_delta,config.window_check_every)
        for i,e in enumerate(series):
            for detector in detectors.values(): detector.update(e,i)
        detail={}
        for name,d in detectors.items():
            detail[name]=dict(available=True,alarm=d.alarm_at is not None,alarm_at=d.alarm_at,samples=len(series),
                              final_statistic=getattr(d,"statistic",getattr(d,"cumulative",None)))
            if isinstance(d,HoeffdingWindowDetector):
                detail[name].update(cut=d.cut,mean_difference=d.mean_difference,bound=d.bound)
        for name,reason in unavailable.items():
            detail[name]=dict(available=False,reason=reason,alarm=False,alarm_at=None,samples=len(series))
        count=sum(x["alarm"] for x in detail.values()); available=len(detectors)
        status="drift_alert" if available>=2 and count>=2 else "single_method_warning" if count else "no_alarm_observed"
        results[cls]=dict(status=status,n=len(series),baseline_error_rate=baseline,detector_count=available,detectors=detail)
    monitored=[k for k,v in results.items() if v["status"]!="insufficient_feedback"]
    unmonitored=[k for k,v in results.items() if v["status"]=="insufficient_feedback"]
    if not monitored: status,reason="abstain","insufficient_feedback"
    elif any(v["status"]=="drift_alert" for v in results.values()): status,reason="drift_alert","two_or_more_algorithms"
    elif any(v["status"]=="single_method_warning" for v in results.values()): status,reason="single_method_warning","one_algorithm"
    else: status,reason="no_alarm_observed","no_detector_triggered"
    return dict(source_id=source,status=status,reason=reason,monitored_classes=monitored,
                unmonitored_classes=unmonitored,classes=results,calibration_updated=False,integrity_verified=False,
                warning="No alarm is not proof of stable accuracy; labels and a matched environment are required.")
