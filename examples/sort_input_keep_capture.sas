/* Original KEEP timing, descriptor order and stable payload identity witness. */
data raw;
  infile datalines dsd;
  input Zebra :$3. Alpha Serial Discard :$2.;
  datalines4;
B,2,1,X
A,.,2,Y
A,-2,3,Z
A,2,4,U
A,2,5,V
a,-1,6,W
,9,7,M
B,.,8,N
;;;;
run;
title "Raw snapshot";
proc print data=raw;
run;
proc sort data=raw(keep=Serial Alpha Zebra) out=selected nodupkey;
  by Zebra Alpha;
run;
title "Selected snapshot";
proc print data=selected;
run;
proc sort data=selected(keep=Serial Zebra) out=serial_order;
  by Serial;
run;
title;
