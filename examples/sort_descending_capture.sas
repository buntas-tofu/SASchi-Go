/* Original mixed-direction order, missing placement and stable survivor witness. */
data intake;
  infile datalines dsd;
  input Zone :$3. Value Serial;
  datalines4;
B,2,1
A,.,2
A,-2,3
A,2,4
A,2,5
a,-.5,6
,9,7
B,.,8
;;;;
run;
proc sort data=intake out=ranked;
  by Zone descending Value;
run;
proc sort data=ranked out=survivors nodupkey;
  by descending Zone Value;
run;
