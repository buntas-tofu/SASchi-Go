proc fcmp outlib=work.functions.Calendar;
 function usr_monday(d) $9;
  x=intnx('week.2',d,0);
  return(put(x,date9.));
 endsub;
 function usr_friday(d) $9;
  x=intnx('week.7',d,1)-1;
  return(put(x,date9.));
 endsub;
quit;
options cmplib=work.functions;
proc format;
 value usr_begin other=[usr_monday()];
 value usr_close other=[usr_friday()];
run;
data deliveries;
 infile cards;
 input customer shipped :date9. orderid;
 cards;
10 31DEC1959 101
10 01JAN1960 102
11 02JAN1960 103
11 03JAN1960 104
12 04JAN1960 105
12 29FEB2000 106
13 31DEC2023 107
13 01JAN2024 108
14 . 109
;
run;
proc report data=deliveries nowd;
 columns customer orderid shipped ('Window' shipped=beginning shipped=ending);
 define customer / order 'Customer';
 define orderid / format=10. 'Order';
 define shipped / display format=weekdate. 'Delivered';
 define beginning / display format=usr_begin12. 'First';
 define ending / display format=usr_close12. 'Last';
 title 'Week callbacks';
run;
title;
