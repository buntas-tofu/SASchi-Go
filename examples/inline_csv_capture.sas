/* Original bounded comma and range state witness. */
data capture(keep=seq total x1 x2 before scratch);
retain total 0;
infile datalines dlm=',' firstobs=2;
input x1-x2;
before=scratch;
scratch=x1;
seq=_n_;
total+x1;
output;
if x2 ne . then x1=99;
if x2 ne . then output;
put total= seq=;
datalines;
first,second
1,,2,ignored
.,5
4,.
7
;
run;
data ranges;
input v62-v64;
summed=sum(v62,v63,v64);
output;
cards;
1 . 3
. . .
;
run;
