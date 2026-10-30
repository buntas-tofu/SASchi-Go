/* Original row-driven numeric composition witness; repository/base-R only. */
data shaped(keep=scratch ratio carried before key total);
retain total 0;
set incoming(drop=excluded);
trigger=1**1;
before=excluded;
if key=1 then excluded=7;
carry=carry+1;
carried=carry;
ratio=x/3;
total+ratio;
if key=1 then scratch=ratio;
if key=2 then output;
if key=3 then output;
put key ratio before excluded;
run;

data follow(drop=ratio before scratch);
set shaped(keep=scratch before total ratio carried key);
again=ratio**2;
put key again carried;
run;

data fresh(keep=answer);
answer=constant('pi')/6;
hidden=sin(answer);
output;
answer=2*answer;
output;
put hidden;
run;
