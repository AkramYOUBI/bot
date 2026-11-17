#!/bin/sh
npm i -g dukascopy-node >/dev/null 2>&1
# Telecharge H1 Dukascopy (bid) 2019 -> aujourd'hui
for i in xauusd xagusd usa500idxusd usatechidxusd usa30idxusd deuidxeur gbridxgbp jpnidxjpy eurusd gbpusd usdjpy audusd usdcad usdchf nzdusd eurjpy gbpjpy; do
  dukascopy-node -i $i -from 2019-01-01 -to 2026-11-17 -t h1 -p bid -v -f csv -dir /data -fn ${i}_h1 -s >/dev/null 2>&1 &
  sleep 1
done
wait
