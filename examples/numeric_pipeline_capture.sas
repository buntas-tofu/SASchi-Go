/* Original inline measurement stream; repository/base-R policy evidence. */
data pipeline(keep=seq total accumulated rolling early);
retain accumulated 0;
array bucket{3} a1-a3;
input x total;
trigger=1**1;
seq=_n_;
j=1;
do while(j<=3);
  bucket{j}=x/j;
  j=j+1;
end;
rolling=sum(of bucket{*});
accumulated+rolling;
total+rolling;
output;
early=rolling/3;
do until(j>=6);
  total+1/3;
  j=j+1;
end;
output;
put seq rolling total;
datalines;
1 0
. .
3 10
;
run;

data fresh(keep=answer);
array a{2} first second;
trigger=1**1;
a{1}=1/3;
a{2}=2/3;
answer=sum(of a{*});
output;
run;
