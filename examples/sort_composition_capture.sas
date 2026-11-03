/* Original DROP and directed projection ordering with immutable snapshots. */
data raw;
  infile datalines dsd;
  input Zebra :$3. Alpha Payload Scrap :$2. Echo :$2.;
  datalines4;
B,2,10,X,p
A,.,20,Y,q
A,-2,30,Z,r
A,2,40,U,s
A,2,50,V,t
a,-1,60,W,u
,9,70,M,v
B,.,80,N,w
A,2,40,U,s
B,2,90,P,x
,.,100,Q,y
a,-1,110,R,z
;;;;
run;
proc sort data=raw(drop=Echo Scrap) out=dropped nodupkey;
  by Zebra Alpha;
run;
title "Ascending DROP snapshot";
proc print data=dropped;
run;
proc sort data=raw(keep=Payload Alpha Zebra Scrap) out=directed nodupkey;
  by Zebra descending Alpha;
run;
proc sort data=raw(drop=Echo Scrap) out=two_directions nodupkey;
  by descending Zebra descending Alpha;
run;
title "Directed KEEP snapshot";
proc print data=directed;
run;
proc sort data=directed(drop=Scrap) out=late;
  by descending Payload Zebra;
run;
proc sort data=dropped(keep=Payload Zebra) out=legacy_keep;
  by Payload;
run;
proc sort data=legacy_keep out=legacy_plain;
  by Zebra;
run;
proc sort data=raw out=legacy_directed;
  by descending Payload;
run;
title;
