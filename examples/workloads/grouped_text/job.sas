/* Original synthetic character events. Repository evidence, no live SAS. */
proc sort data=raw out=ordered;
  by team seq;
run;

data prepared;
  length short $8;
  length combined $40;
  set ordered;
  where include=1;
  short=payload;
  combined=catx('|',tag,short);
  actual_len=lengthn(payload);
  storage_len=lengthc(payload);
  backwards=reverse(payload);
run;

data snapshots;
  length entry_kind $5;
  retain total 0;
  retain n_in_group 0;
  set prepared;
  by team;
  if first.team then total=0;
  if first.team then n_in_group=0;
  if value=. then value=0;
  total=total+value;
  n_in_group=n_in_group+1;
  entry_kind='row';
  output;
  if last.team then entry_kind='close';
  if last.team then output;
run;
