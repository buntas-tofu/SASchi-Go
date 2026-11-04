data flights;
infile datalines;
input delay destination $3.;
datalines;
-2 ABC
0 DEF
1 GHI
2 JKL
9 MNO
10 PQR
11 STU
26 VWX
;
run;
proc format;
picture usr_nine low-<0='Early' 0='On time' 1='1 minute'
1<-10='09 minutes' 10<-high='More than 10' (noedit);
picture usr_double low-<0='Early' 0='On time' 1='1 minute'
1<-10='99 minutes' 10<-high='More than 10' (noedit);
picture usr_edited low-<0='Early' 0='On time' 1='1 minute'
1<-10='09 minutes' 10<-high='09 late';
run;
proc report data=flights nowd;
column delay delay=two delay=digits delay=plain;
define delay / display format=usr_nine. 'Optional zero';
define two / format=usr_double. 'Leading zero';
define digits / format=usr_edited. 'Edited message';
define plain / display format=comma12. 'Raw';
title 'Integer pictures';
run;
