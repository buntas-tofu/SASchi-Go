/* Original bounded numeric helper and stored-format composition witness. */
data metrics;
  set raw;
  magnitude=abs(x);
  direction=sign(x);
  ceiling=ceil(x);
  floor=floor(x);
  shown=put(magnitude,8.2);
  output;
  put shown;
run;
