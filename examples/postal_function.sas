proc format;
 value $usr_region '0200'-'0299'='ACT' '0800'-'0999'='NT' '1000'-'1999'='NSW' '8000'-'8999'='VIC';
run;
proc fcmp outlib=work.functions.Regions;
 function usr_region_of(country $,code $) $5;
  if upcase(country)='AU' then region=put(code,$usr_region.);
  else if upcase(country)='US' then region=zipstate(code);
  else region=' ';
  return(region);
 endsub;
quit;
options cmplib=work.functions;
data contacts;
 infile cards dlm=',' dsd;
 input id :$10. person :$30. city :$15. postal :$5. country :$2.;
 cards;
1,"River, Lee","Holyoke",01040,US
2,"Kai ""K"" North",Canberra,0200,au
3,Avery,Unknown,00000,ZZ
4,Quinn,Darwin,0800,AU
5,Jordan,Cary,27511,US
6,Sam,Sydney,1225,AU
;
run;
proc sort data=contacts;
 by country;
run;
proc report data=contacts nowd;
 columns country city postal region id person;
 by country;
 define region / computed 'State/Province';
 compute region / char length=5;
  region=usr_region_of(country,postal);
 endcomp;
 title 'Country regions';
run;
title;
