/* Original physical-record input and stable sorting witness. */
data scores;
  infile datalines dsd;
  input Person :$8. Topic :$7. Score;
  datalines4;
 Nia ,Math,8
Omar,Reading,.
Nia,Math,9
,Reading,4
Ivo;Q,Logic,1.5
A\B,,
;;;;
run;
proc sort data=scores out=ordered;
  by Person Topic;
run;
