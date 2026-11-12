/* Original explicit-delimiter and fixed-width word witness. */
data words;
  set raw;
  head=scan(text,1,'|');
  tail=scan(text,-1,'|');
  n=countw(text,'|');
  m=countw(text,'|','M');
  output;
  put head;
  put tail;
run;
