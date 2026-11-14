# Independent R composition witnesses; no Python implementation is imported.
source(file.path(here,'function_wave2_oracles.R'))
source(file.path(here,'function_wave3_oracles.R'))
cx_num<-function(x) {if(!is.numeric(x)||length(x)!=1L||is.nan(x)||(!is.na(x)&&(!is.finite(x)||abs(x)>1000000))) stop('numeric domain');x}
cx_truth<-function(x) {!is.na(cx_num(x)) && x!=0}
cx_cmp<-function(a,b,op) {
 if(is.character(a)!=is.character(b)) stop('comparison type')
 if(is.character(a)) {w<-max(nchar(a,type='bytes'),nchar(b,type='bytes'));a<-store(a,w);b<-store(b,w)} else {
  a<-cx_num(a);b<-cx_num(b);if(is.na(a)&&is.na(b)) {a<-0;b<-0} else if(is.na(a)) {a<--Inf} else if(is.na(b)) {b<--Inf}
 }
 as.numeric(switch(op,eq=a==b,ne=a!=b,lt=a<b,le=a<=b,gt=a>b,ge=a>=b,stop('comparison')))
}
cx_plus<-function(a,b,subtract=FALSE) {a<-cx_num(a);b<-cx_num(b);if(any(!is.na(c(a,b)) & c(a,b)!=floor(c(a,b)))) stop('integer arithmetic');v<-if(anyNA(c(a,b))) NA_real_ else if(subtract) a-b else a+b;cx_num(v)}
cx_call<-function(name,args) {
 if(name %in% c('upcase','lowcase','strip','trim','trimn','compbl')) {
  x<-args[[1]];ws_ascii(x)
  return(switch(name,upcase=upper_text(x),lowcase=lower_text(x),strip=strip_text(x),trim={z<-sub(' +$','',x);if(nzchar(z)) z else ' '},trimn=sub(' +$','',x),compbl=ws_call_value('compbl',args)))
 }
 if(name %in% c('propcase','dequote','transtrn')) return(txt_call_value(name,args))
 if(name=='substrn') return(search_call_value(name,args))
 if(name=='cats') return(cat_call_value(name,args))
 if(name=='catx') {
  values<-lapply(args,strip_text);delim<-args[[1]];values<-values[-1L];values<-values[vapply(values,nzchar,TRUE)];z<-paste(unlist(values),collapse=delim);if(nchar(z,type='bytes')>200) stop('buffer');return(z)
 }
 if(name %in% c('missing','cmiss')) return(sum(vapply(args,missing_value,0)))
 if(name %in% c('length','lengthn')) {ws_ascii(args[[1]]);v<-nchar(sub(' +$','',args[[1]]),type='bytes');return(if(name=='length') max(1,v) else v)}
 if(name %in% c('verify','anyalpha','anydigit','anyalnum','anyspace','notdigit')) return(val_call_value(name,args))
 if(name %in% c('anylower','anyupper','anypunct','anyxdigit','notalpha','notalnum','notspace')) return(pos_call_value(name,args))
 if(name %in% c('largest','smallest')) return(rank_call_value(name,args))
 if(name %in% c('ceilz','floorz','intz','roundz','modz')) return(zero_call_value(name,args))
 if(name %in% c('ifn','ifc')) return(sel_call_value(name,args))
 values<-vapply(args,cx_num,0)
 if(name=='abs') return(abs(values[1]))
 if(name=='sign') return(sign(values[1]))
 if(name=='n') return(sum(!is.na(values)))
 if(name=='nmiss') return(sum(is.na(values)))
 if(name=='coalesce') return(if(any(!is.na(values))) values[which(!is.na(values))[1]] else NA_real_)
 present<-values[!is.na(values)]
 if(!length(present)) return(NA_real_)
 if(name=='min') return(min(present))
 if(name=='max') return(max(present))
 if(name=='sum') {if(any(present*1024!=floor(present*1024))) stop('exact dyadic sum');return(cx_num(sum(present)))}
 stop('name')
}
C<-function(name,...) cx_call(name,list(...))
M<-function(x) as.numeric(missing_value(x))
N<-function(x) cx_num(x)
B<-function(x) as.numeric(cx_truth(x))
L<-function(x) paste0(if(is.na(x)) '.' else sprintf('%.17g',x),' ')
T<-function(x) paste0(strip_text(x),' ')
