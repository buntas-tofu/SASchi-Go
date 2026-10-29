/* Original DS-044 record scheduling and snapshot witness. */
data capture;
retain total 0;
input a b;
before=scratch;
if a < b then scratch=a;
total + a;
seq=_n_;
output;
a=99;
if b > 0 then output;
put total= seq=;
datalines;
1
2 999
. 5
4 . ignored
8
;
run;
