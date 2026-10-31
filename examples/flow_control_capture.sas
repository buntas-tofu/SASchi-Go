/* Original scalar-flow state and publication witness for maintainer review. */
data counted;
  n=0;
again:
  n=n+1;
  if n<3 then goto again;
  put n;
  output;
  stop;
run;

data saved(keep=x total scratch);
  retain total 0;
  input x;
  if 0 then future=9;
  if x=2 then return;
  link adjust;
  put x total scratch;
  output;
  return;
adjust:
  scratch=x*2;
  total+scratch;
  return;
cards;
1
2
3
;
run;

data tail;
  x=0;
  link bump;
  put x;
  output;
  stop;
bump:
  x=x+1;
  return;
run;
