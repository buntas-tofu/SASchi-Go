/* Original stable DUPOUT partitions, controlled replacement and snapshots. */
data raw;
  infile datalines dsd;
  input Zebra :$3. Alpha Payload Mark :$2.;
  datalines4;
B,2,10,X
A,1,20,Y
B,2,30,Z
A,.,40,U
,9,50,V
A,1,60,W
a,-1,70,M
B,.,80,N
A,1,60,W
,9,90,P
B,2,10,X
A,.,100,Q
C,-2,110,R
a,-1,120,S
;;;;
run;
proc sort data=raw out=ranked;
  by descending Payload;
run;
title "Ranked before replacement";
proc print data=ranked;
run;
proc sort data=raw out=firsts dupout=extras nodupkey;
  by Zebra Alpha;
run;
title "First encounter survivors";
proc print data=firsts;
run;
proc sort data=ranked dupout=ranked_removed nodupkey;
  by Zebra Alpha;
run;
title "Removed after replacement";
proc print data=ranked_removed;
run;
title;
