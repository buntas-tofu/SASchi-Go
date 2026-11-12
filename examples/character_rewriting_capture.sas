/* Original character deletion, mapping and substring replacement witness. */
data edits;
  set raw;
  tight=compress(text);
  kept=compress(text,'Ab','IK');
  mapped=translate(text,'12','ab');
  changed=tranwrd(text,'ab','XY');
  output;
  put tight;
  put mapped;
run;
