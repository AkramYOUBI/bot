#!/bin/sh
npm i -g dukascopy-node >/dev/null 2>&1
for i in btcusd ethusd lightcmdusd brentcmdusd fraidxeur eusidxeur ausidxaud hkgidxhkd espidxeur; do
  dukascopy-node -i $i -from 2019-01-01 -to 2026-11-17 -t h1 -p bid -v -f csv -dir /data -fn ${i}_h1 -s >/dev/null 2>&1 &
  sleep 1
  dukascopy-node -i $i -from 2019-01-01 -to 2026-11-17 -t h1 -p ask -v -f csv -dir /data -fn ${i}_h1_ask -s >/dev/null 2>&1 &
  sleep 1
done
wait
