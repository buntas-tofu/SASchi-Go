/* Original DS-041 captured controls and nested numeric alias composition. */
data capture;
array cell{3} first second third;
start=1; finish=3; stride=1; total=0;
do i=start to finish by stride;
  start=9; finish=0; stride=-1;
  do j=i to 3 by i;
    before=cell[j];
    if cell[j]=. then cell[j]=0;
    cell[j]=cell[j]+i;
    total=total+i;
    seen=_n_;
    output;
  end;
end;
after=i; inner_after=j;
output;
put total= i= j=;
run;
