/* Original measurement transformation pipeline; repository/base-R evidence. */
data transformed(keep=seq root logged combined array_total running stage);
retain running 0;
array component{2} root logged;
input x;
seq=_n_;
root=sqrt(x);
logged=log(1+x);
combined=sum(root,logged,.);
array_total=sum(of component{*});
running+combined;
stage=0;
do while(stage<1);
  stage=stage+1;
  output;
end;
do until(stage>=2);
  stage=stage+1;
end;
output;
put seq combined running;
datalines;
0
3
.
;
run;

data fresh(keep=root logged combined running);
root=sqrt(4);
logged=log(1);
combined=sum(root,logged);
running+combined;
output;
run;
