/* Original fixed-pointer and procedure-local report witness. */
proc format;
  invalue usr_grade 'High'=4 'Low'=1 'Mid'=2;
run;
data sample;
  input id $ @4 word $4. @4 n usr_grade. @9 backup usr_grade.;
datalines;
A1 High Low !
B2 2    High!
C3 Low  3   !
D4 Mid  Mid !
E5 High Low !
;
run;
title '  Intake  ';
proc print data=sample label noobs;
  label word='Raw word' n='Score';
run;
proc means data=sample;
run;
title;
