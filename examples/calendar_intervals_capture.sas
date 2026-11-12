/* Original calendar cohort and stored DATE9 composition witness. */
data cohorts;
  set raw;
  year=year(d);
  month=month(d);
  day=day(d);
  months=intck('MONTH',d,ending);
  back=intck('MONTH',ending,d);
  shifted=intnx('MONTH',d,move,'S');
  boundary=intnx('MONTH',d,move,'E');
  shown=put(shifted,date9.);
  output;
  put shown;
run;
