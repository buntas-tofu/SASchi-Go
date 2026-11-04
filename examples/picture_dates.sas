proc format;
picture usr_iso low-high='%Y|%b|%0d   ' (datatype=date);
run;
data team;
infile cards;
input label :$8. arrived :date9. id;
cards;
A 31DEC1989 1
B 01APR1990 2
C 31MAR1993 3
D 01APR1993 4
E . 5
;
run;
proc print data=team;
var id label arrived;
format arrived usr_iso.;
title 'Date pictures';
run;
proc format;
picture usr_epoch low-<'01APR1990'd='Before'
'01APR1990'd-'31MAR1993'd='%B %d   ' (datatype=date)
other='After';
run;
proc print data=team(obs=4);
var arrived id;
format arrived usr_epoch.;
title 'Intervals';
run;
