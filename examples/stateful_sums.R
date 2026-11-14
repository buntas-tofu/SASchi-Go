here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'stateful_wave_oracles.R'))
required<-c("data sum_rows","length canon $24","length trace $8","retain offset 5","set raw","canon=upcase(compbl(dequote(strip(code))))","if enable then do","total+abs(amount-expected)","valid+n(amount,expected)","net+(amount-expected)","end","offset=offset+1","simple=amount+expected","trace=ifc(enable,'ADD','SKIP')","output","put 'sum'","run")
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
 cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 for(i in seq_len(nrow(cases))) cat(tryCatch(encode(sx_call(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
 text<-paste(readLines(args[2],warn=FALSE),collapse='\n')
 parts<-trimws(gsub('[[:space:]]+',' ',strsplit(text,';',fixed=TRUE)[[1]]));parts<-parts[nzchar(parts)]
 if(!identical(parts,required)) stop('original source sequence')
 input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 expected_names<-c("rid","code","amount","expected","enable","batch","limit")
 if(!identical(names(input),expected_names)) stop('input column order')
 rows<-lapply(seq_len(nrow(input)),function(i) {
   row<-lapply(input[i,],function(x) if(nzchar(x)) as.numeric(x) else NA_real_)
   row[[2]]<-store(input[[2]][i],24L)
   names(row)<-expected_names;row
 })
 cat('STATEMENTS|',length(required),'\n',sep='')
 cat('COLUMNS|raw|rid,code,amount,expected,enable,batch,limit\n')
 cat('COLUMNS|sum_rows|canon,trace,offset,rid,code,amount,expected,enable,batch,limit,total,valid,net,simple\n')
 for(row in rows) emit("raw",row)
 offset<-5;total<-0;valid<-0;net<-0;logs<-character()
 for(row in rows) {
  canon<-C('upcase',C('compbl',C('dequote',C('strip',row$code))))
  if(cx_truth(row$enable)) {total<-sx_add(total,C('abs',cx_plus(row$amount,row$expected,TRUE)));valid<-sx_add(valid,C('n',row$amount,row$expected));net<-sx_add(net,cx_plus(row$amount,row$expected,TRUE))}
  offset<-sx_state(cx_plus(offset,1));simple<-cx_plus(row$amount,row$expected)
  trace<-C('ifc',row$enable,'ADD','SKIP')
  emit('sum_rows',c(list(store(canon,24L),store(trace,8L),offset),row,list(total,valid,net,simple)))
  logs<-c(logs,'sum')
 }
 for(record in logs) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
