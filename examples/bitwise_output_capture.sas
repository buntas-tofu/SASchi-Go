/* Original explicit diagnostic policy witness with overwrite and spelling. */
data _null_;
  Seed=13;
  mask=6;
  Bits=bxor(Seed,mask);
  Seed=band(Bits,mask);
  Shift=blshift(Seed,3);
  put _all_;
run;
