here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'stateful_wave_oracles.R'))
required<-c("data batch_summary","length batch_label $24","length status $8","retain seen 0","retain accepted 0","retain rejected 0","retain net 0","retain magnitude 0","retain worst 0","set ledger","by batch","batch_label=upcase(compbl(strip(label)))","if first.batch then do","seen=0","accepted=0","rejected=0","net=0","magnitude=0","worst=0","end","seen+1","if n(amount,expected)=2 then do","delta=amount-expected","accepted+1","net+delta","magnitude+abs(delta)","worst=max(worst,abs(delta))","end","else rejected+1","if last.batch then do","status=ifc(rejected=0 and worst<=limit,'READY','REVIEW')","output","end","run","data review_batches","set batch_summary","where status='REVIEW'","run")
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
 cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 for(i in seq_len(nrow(cases))) cat(tryCatch(encode(sx_call(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
 text<-paste(readLines(args[2],warn=FALSE),collapse='\n')
 parts<-trimws(gsub('[[:space:]]+',' ',strsplit(text,';',fixed=TRUE)[[1]]));parts<-parts[nzchar(parts)]
 if(!identical(parts,required)) stop('original source sequence')
 input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 expected_names<-c("batch","label","amount","expected","limit")
 if(!identical(names(input),expected_names)) stop('input column order')
 rows<-lapply(seq_len(nrow(input)),function(i) {
   row<-lapply(input[i,],function(x) if(nzchar(x)) as.numeric(x) else NA_real_)
   row[[2]]<-store(input[[2]][i],16L)
   names(row)<-expected_names;row
 })
 cat('STATEMENTS|',length(required),'\n',sep='')
 cat('COLUMNS|ledger|batch,label,amount,expected,limit\n')
 cat('COLUMNS|batch_summary|batch_label,status,seen,accepted,rejected,net,magnitude,worst,batch,label,amount,expected,limit,delta\n')
 cat('COLUMNS|review_batches|batch_label,status,seen,accepted,rejected,net,magnitude,worst,batch,label,amount,expected,limit,delta\n')
 for(row in rows) emit("ledger",row)
 sx_order(rows,'batch');seen<-0;accepted<-0;rejected<-0;net<-0;magnitude<-0;worst<-0;summary<-list()
 for(i in seq_along(rows)) {
  row<-rows[[i]];first<-if(i==1L) TRUE else !sx_equal(rows[[i-1L]]$batch,row$batch);last<-if(i==length(rows)) TRUE else !sx_equal(rows[[i+1L]]$batch,row$batch)
  label<-C('upcase',C('compbl',C('strip',row$label)));delta<-NA_real_
  if(first) {seen<-0;accepted<-0;rejected<-0;net<-0;magnitude<-0;worst<-0}
  seen<-sx_add(seen,1)
  if(C('n',row$amount,row$expected)==2) {delta<-cx_plus(row$amount,row$expected,TRUE);accepted<-sx_add(accepted,1);net<-sx_add(net,delta);magnitude<-sx_add(magnitude,C('abs',delta));worst<-sx_state(C('max',worst,C('abs',delta)))} else rejected<-sx_add(rejected,1)
  if(last) {status<-C('ifc',as.numeric(rejected==0 && cx_truth(cx_cmp(worst,row$limit,'le'))),'READY','REVIEW');out<-c(list(store(label,24L),store(status,8L),seen,accepted,rejected,net,magnitude,worst),row,list(delta));summary[[length(summary)+1L]]<-out;emit('batch_summary',out)}
 }
 for(out in summary) if(out[[2]]==store('REVIEW',8L)) emit('review_batches',out)
} else stop('mode')
