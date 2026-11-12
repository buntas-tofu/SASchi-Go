/* Original typed missing-value and row-summary witness. */
data filled;
  set raw;
  flag=missing(name);
  count=n(a,b);
  miss=nmiss(a,b);
  mixed=cmiss(name,a,b);
  choice=coalesce(a,b);
  label=coalescec(name,backup,'NA');
  avg=mean(a,b);
  output;
  put label;
run;
