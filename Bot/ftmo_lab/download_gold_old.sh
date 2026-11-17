#!/bin/sh
npm i -g dukascopy-node >/dev/null 2>&1
dukascopy-node -i xauusd -from 2007-01-01 -to 2019-01-01 -t h1 -p bid -v -f csv -dir /data -fn xauold_h1 -s >/dev/null 2>&1 &
sleep 1
dukascopy-node -i xauusd -from 2007-01-01 -to 2019-01-01 -t h1 -p ask -v -f csv -dir /data -fn xauold_h1_ask -s >/dev/null 2>&1 &
wait
