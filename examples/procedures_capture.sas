/* Original supplied-data procedure workflow; repository policy, not a SAS log capture. */
proc sort data=raw out=ordered;
  by g;
run;
proc means data=ordered noprint vardef=df;
  by g;
  var x;
  output out=summary n=nobs nmiss=nmissing mean=avg var=variance / noinherit;
run;
proc print data=summary noobs;
  var g _type_ _freq_ nobs nmissing avg variance;
run;
