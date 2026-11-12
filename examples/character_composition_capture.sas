/* Original character and missing-value composition witness. */
data prepared;
  set raw;
  upper=upcase(text);
  lower=lowcase(text);
  first=scan(upper,1,'|');
  last=scan(upper,-1,'|');
  words=countw(upper,'|');
  at=index(upper,'AB');
  found=find(upper,'ab','I');
  tight=compress(first);
  mapped=translate(tight,'12','AB');
  replaced=tranwrd(mapped,'12','XY');
  blank=missing(backup);
  gaps=cmiss(backup,n);
  chosen=coalescec(backup,replaced,'NA');
  output;
  put chosen;
run;
