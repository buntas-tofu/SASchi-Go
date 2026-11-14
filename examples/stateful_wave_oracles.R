# Independent R state schedules and value kernels, frozen before translator work.
source(file.path(here,'composition_wave_oracles.R'))
sx_state<-function(x) {x<-cx_num(x);if(!is.na(x) && x!=floor(x)) stop('integral retained state');x}
sx_add<-function(a,b) {a<-sx_state(a);b<-sx_state(b);sx_state(sum(c(a,b),na.rm=TRUE))}
sx_equal<-function(a,b) if(is.na(a) || is.na(b)) is.na(a)&&is.na(b) else a==b
sx_order<-function(rows,key) {
 keys<-vapply(rows,function(row) cx_num(row[[key]]),0)
 if(length(keys)>1L) for(i in 2:length(keys)) if((is.na(keys[i]) && !is.na(keys[i-1L])) || (!is.na(keys[i]) && !is.na(keys[i-1L]) && keys[i]<keys[i-1L])) stop('sorted numeric BY input required')
}
sx_call<-function(name,args) if(name=='accumulate') do.call(sx_add,args) else cx_call(name,args)
