/* First-party exact numeric exchange witness. */
data samples(keep=c1 c2 c3 total retained_seen);
retain grand 0;
infile datalines dlm=',' firstobs=2;
file "measurements.csv" dlm=',';
input c1-c3;
if _n_=1 then put "C1,C2,C3,Total";
total=sum(of c1-c3);
grand+total;
retained_seen=grand;
put c1-c3 total;
output;
c1=99;
output;
datalines;
A,B,C
1,,2
3,ignored-tail
.,4,8
.,.,.
9,10
;
run;
data lists;
x1=7;
x2=.;
x3=9;
total=sum(of x1-x3);
put x1-x3 total;
run;
data _null_;
put "after";
run;
