/* Original finite informat and repeated-column input witness. */
proc format;
  invalue usr_rating 'High'=9 'Low'=2 'Medium'=5;
run;
data ratings;
  input person $ @10 original $6. @10 rating usr_rating.;
datalines;
A1       High  
B02      7     
C3       Medium
D04      Low   
;
run;
proc format;
  invalue usr_sign 'Plus'=1 'Minus'=-1;
run;
data signs;
  input token $ @4 original $5. @4 sign usr_sign.;
datalines;
p  Plus 
n  Minus
z  0    
;
run;
