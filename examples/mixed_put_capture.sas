/* Original DS-042 alias, output and missing-field witness. */
data records;
  array a x y;
  do i=1 to 2;
    a[i]=i;
    put 'i:' i 'x:' x 'y:' y;
    output;
  end;
  total=sum(of a[*]);
  put 'total:' total;
  output;
run;
