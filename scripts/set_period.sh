#!/usr/bin/env bash
# Set the 1-number reporting period used for ground truth in all three places:
#   nwdafcfg.yaml samplingInterval (-> SMF/UPF repPeriod), smfcfg.yaml urrPeriod (PFCP URR),
#   UPF-EES*.yaml ees.periodSec (EES aggregator tick in the May-13 UPF build).
# usage: set_period.sh <seconds>
set -eu
P=$1; C=$HOME/free5gc-NWDAF/5G_Infrastructure/config/5GC
sed -i -E "s/^(      samplingInterval: )[0-9]+/\1$P/" $C/nwdafcfg.yaml
sed -i -E "s/^(  urrPeriod: )[0-9]+/\1$P/" $C/smfcfg.yaml
sed -i -E "s/^(  periodSec: )[0-9]+/\1$P/" $C/UPF-EES.yaml $C/UPF-EES2.yaml
grep -H -E "^      samplingInterval:|^  urrPeriod:|^  periodSec:" $C/nwdafcfg.yaml $C/smfcfg.yaml $C/UPF-EES.yaml $C/UPF-EES2.yaml | cut -c1-110
