data dates;
infile cards;
input id sex :$1. amount born :date9. hired :date9.;
cards;
1 F 7 31DEC1959 01JAN1960
2 M -2 01JAN1960 01JAN1970
3 F . . 29FEB2000
;
run;
proc format;
value cohort low-'31DEC1959'd=[weekdate37.]
'01JAN1960'd-'31DEC1999'd=[worddate20.]
'01JAN2000'd-high='New era';
run;
title 'Dates';
proc print data=dates;
format born hired cohort.;
run;
title;
