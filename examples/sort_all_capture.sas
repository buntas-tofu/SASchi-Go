/* Original descriptor-order permutation, exact duplicates and missing witness. */
data first;
  infile datalines dsd;
  input Zebra :$3. Alpha Middle :$3.;
  datalines4;
B,1,z
A,2,y
A,1,x
A,1,x
,,m
a,-1,n
B,.,w
;;;;
run;
proc sort data=first out=first_unique nodupkey;
  by _all_;
run;
data second;
  infile datalines dsd;
  input Alpha Zebra :$3. Middle :$3.;
  datalines4;
1,B,z
2,A,y
1,A,x
1,A,x
,,m
-1,a,n
.,B,w
;;;;
run;
proc sort data=second out=second_unique nodupkey;
  by _all_;
run;
