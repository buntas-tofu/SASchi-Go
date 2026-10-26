/* Original synthetic usage ledger. Repository contract evidence, no live SAS. */
data rounded;
  set raw;
  where include=1;
  amount=round(amount,1);
run;

proc sort data=rounded out=ordered;
  by account period seq;
run;
proc sort data=lookup out=keys;
  by account;
run;

data joined;
  merge ordered keys;
  by account;
run;

data snapshots;
  length band $4;
  length code $6;
  length entry_kind $5;
  retain total 0;
  set joined;
  by account;
  where period>0;
  previous=lag(amount);
  change=dif(amount);
  if first.account then previous=.;
  if first.account then change=.;
  if first.account then total=0;
  if amount=. then amount=0;
  total=total+amount;
  adjusted=amount+fee;
  if amount>=10 then band='high';
  else band='base';
  code=catx('-',band,'U');
  entry_kind='row';
  output;
  if last.account then entry_kind='close';
  if last.account then output;
run;
