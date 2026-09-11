/* rounding_program.sas: an original synthetic fixture (no estate material).
   Exercises the SAS ROUND half-away-from-zero law across half-unit
   boundaries. The translator's first end-to-end target (Track A step 3). */
data rounded_values;
  x1 = 0.25;
  r1 = round(x1, 0.1);
  x2 = 9.995;
  r2 = round(x2, 0.01);
  x3 = -2.5;
  r3 = round(x3, 1);
  x4 = 0.125;
  r4 = round(x4, 0.01);
  put r1= r2= r3= r4=;
run;
