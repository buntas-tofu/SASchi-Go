data raw;
    infile datalines dsd;
    input word :$12. code :$4. n;
    datalines4;
beta,B,9
alpha,A,2
beta,A,7
,,
two words,C,-3
alpha,A,4
path\leaf,D,0
Zebra,%,.
;;;;
run;
title '  Intake  ';
proc print data=raw;
run;
title;
proc sort data=raw out=ordered;
    by word code;
run;
title "After ordering";
proc print data=ordered;
run;
title;
