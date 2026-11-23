"""Synthetic labelled-feedback benchmark for V0.2.9 drift monitors."""
from __future__ import annotations
import json,random,statistics,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from protocol_zero.drift import monitor_source
from protocol_zero.reliability import ReliabilityProfile

SEED_BASE=29000; SEEDS=100; CALIBRATION_PER_CLASS=500
STREAM_LENGTH=2500; CHANGE_AT=600; ENVIRONMENT="synthetic-bench-v1"

def calibration_profile(seed):
    rng=random.Random(seed)
    fn=sum(rng.random()<.05 for _ in range(CALIBRATION_PER_CLASS))
    fp=sum(rng.random()<.05 for _ in range(CALIBRATION_PER_CLASS))
    return ReliabilityProfile(source_id="boundary-a",independence_group="uart-hardware-a",
        calibration_set_id=f"calibration-{seed}",environment_id=ENVIRONMENT,
        true_positive=CALIBRATION_PER_CLASS-fn,false_negative=fn,
        true_negative=CALIBRATION_PER_CLASS-fp,false_positive=fp,min_per_class=30)

def error_stream(mode,seed,p0=.05):
    rng=random.Random(seed); out=[]; previous=rng.random()<p0
    for t in range(STREAM_LENGTH):
        if mode=="stationary_iid": p=p0; error=rng.random()<p
        elif mode=="abrupt_increase": p=p0 if t<CHANGE_AT else .20; error=rng.random()<p
        elif mode=="gradual_increase":
            p=p0 if t<CHANGE_AT else p0+.15*min(1.,(t-CHANGE_AT)/1000); error=rng.random()<p
        elif mode=="temporary_spike":
            p=.20 if CHANGE_AT<=t<CHANGE_AT+500 else p0; error=rng.random()<p
        elif mode=="improvement": p=p0 if t<CHANGE_AT else .01; error=rng.random()<p
        elif mode=="stationary_autocorrelated":
            p11=.50; p01=p0*(1-p11)/(1-p0); error=rng.random()<(p11 if previous else p01)
        else: raise ValueError(f"unknown scenario: {mode}")
        previous=bool(error); out.append(bool(error))
    return out

def run_scenario(name,index):
    alarms={"likelihood_cusum":[],"page_hinkley":[],"hoeffding_window":[]}
    consensus=[]; any_alarm=[]; first_alarm=[]; consensus_alarm=[]; pre_change=[]; baselines=[]
    for seed in range(SEEDS):
        profile=calibration_profile(SEED_BASE+seed)
        errors=error_stream(name,SEED_BASE+10000*(index+1)+seed)
        baselines.append((profile.false_negative+.5)/(profile.positive_examples+1))
        feedback=[(True,not e) for e in errors]
        result=monitor_source(profile,feedback,evaluation_set_id=f"{name}-evaluation-{seed}",
                              evaluation_environment_id=ENVIRONMENT)
        detail=result["classes"]["valid_candidates"]["detectors"]
        observed={k:v["alarm_at"] for k,v in detail.items()}
        for key in alarms: alarms[key].append(observed[key])
        times=sorted(v for v in observed.values() if v is not None)
        first=times[0] if times else None
        second=times[1] if len(times)>=2 else None
        first_alarm.append(first); consensus_alarm.append(second)
        count=sum(v is not None for v in observed.values())
        consensus.append(count>=2); any_alarm.append(count>=1)
        pre_change.append(first is not None and first<CHANGE_AT)
    change_modes={"abrupt_increase","gradual_increase","temporary_spike","improvement"}
    first_delays=[x-CHANGE_AT for x in first_alarm if x is not None and x>=CHANGE_AT]
    consensus_delays=[x-CHANGE_AT for x in consensus_alarm if x is not None and x>=CHANGE_AT]
    return {
        "scenario":name,"seeds":SEEDS,"calibration_per_class":CALIBRATION_PER_CLASS,
        "evaluation_stream_length":STREAM_LENGTH,"change_at":CHANGE_AT if name in change_modes else None,
        "mean_smoothed_calibration_fnr":statistics.mean(baselines),
        "detector_alarm_rates":{k:sum(x is not None for x in v)/SEEDS for k,v in alarms.items()},
        "any_detector_alarm_rate":sum(any_alarm)/SEEDS,
        "two_of_three_alert_rate":sum(consensus)/SEEDS,
        "pre_change_alarm_rate":sum(pre_change)/SEEDS if name in change_modes else None,
        "median_first_alarm_index":statistics.median([x for x in first_alarm if x is not None]) if any(x is not None for x in first_alarm) else None,
        "median_first_alarm_delay":statistics.median(first_delays) if first_delays else None,
        "median_two_of_three_alert_delay":statistics.median(consensus_delays) if consensus_delays else None,
        "no_alarm_count":sum(x is None for x in first_alarm),"paired_seeds":True}

def main():
    names=["stationary_iid","abrupt_increase","gradual_increase","temporary_spike","improvement","stationary_autocorrelated"]
    payload={"experiment":"V0.2.9 labelled-feedback drift detection","seed_base":SEED_BASE,
      "scenarios":[run_scenario(n,i) for i,n in enumerate(names)],
      "detector_parameters":{
        "likelihood_cusum":{"target_increase":.15,"threshold":9.0},
        "page_hinkley":{"delta":.02,"threshold":10.0},
        "hoeffding_window":{"min_window":64,"max_window":2048,"delta_per_scan":.01,"check_every":16},
        "alert_policy":"two of three algorithms; agreement is not independent evidence"},
      "limitations":[
        "All streams are synthetic Bernoulli or stationary two-state Markov processes.",
        "Calibration and evaluation use separate random draws and identifiers.",
        "Thresholds are fixed engineering settings, not universally calibrated operating points.",
        "Hoeffding correction is per scan, not time-uniform across repeated scans.",
        "CUSUM and Page-Hinkley assume weakly dependent observations; autocorrelation causes false alarms.",
        "No alarm does not prove stable accuracy; no automatic recalibration, real capture or field validation."]}
    out=Path("experiments/v029_drift_benchmark.json")
    out.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(payload,indent=2))

if __name__=="__main__": main()
