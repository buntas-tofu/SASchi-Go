/* Original empty-descriptor witness; repository/base-R evidence, no live SAS. */
proc sql;
create table contacts (record_id char(8), display_name char(40), region char(2));
quit;

proc sql;
create table widths (_first char(1), boundary char(32767), final_2 char(17));
quit;
