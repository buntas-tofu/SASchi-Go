/* Original rounded arithmetic witness; repository/base-R evidence, no live SAS. */
data capture;
pi=constant('pi');
total=0;
do i=1 to 3;
  total+1/i**2;
end;
if total>1 then selected=sin(pi/6);
missing=.;
total+missing;
output;
put total selected missing;
total=total+1/3;
output;
put total;
run;

data fresh;
pi=constant('pi');
answer=atan(1)*4;
output;
put answer;
run;
