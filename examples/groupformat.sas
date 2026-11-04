data wages;
infile cards;
input id salary hired :date9.;
cards;
1 4 01JAN1960
2 4 02JAN1960
3 8 03JAN1960
4 10 04JAN1960
5 19 05JAN1960
6 22 06JAN1960
;
run;
proc format;
value usr_band low-<10='Low' 10-<20='Mid' 20-high='High';
run;
data ends;
set wages;
by groupformat salary;
format salary usr_band.;
if first.salary then output;
if last.salary then output;
run;
proc report data=ends nowd;
columns id salary salary=band hired;
define salary / display format=dollar12.;
define hired / format=date9.;
define band / format=usr_band. 'Pay band';
title 'Group endpoints';
run;
title;
