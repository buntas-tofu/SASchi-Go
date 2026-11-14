here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'stateful_wave_oracles.R'))
required<-c("data grouped_rows","length canon $24","length phase $8","retain peak 0","retain total 0","set raw","by batch","canon=upcase(compbl(dequote(strip(code))))","if first.batch then do","peak=0","total=0","end","total+abs(amount-expected)","peak=max(peak,abs(amount-expected))","if first.batch and n(amount,expected)<2 then do","phase='FIRST'","output","end","if last.batch then do","phase=ifc(total>5 or n(amount,expected)<2,'REVIEW','READY')","output","end","put 'group'","run")
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
 cat('COLUMNS|grouped_rows|canon,phase,peak,total,rid,code,amount,expected,enable,batch,limit\n')
 for(row in rows) emit("raw",row)
 sx_order(rows,'batch');peak<-0;total<-0;logs<-character()
 for(i in seq_along(rows)) {
  row<-rows[[i]];first<-i==1L || sx_equal(rows[[i-1L]]$batch,row$batch);first<-if(i==1L) TRUE else !sx_equal(rows[[i-1L]]$batch,row$batch)
  last<-if(i==length(rows)) TRUE else !sx_equal(rows[[i+1L]]$batch,row$batch)
  canon<-C('upcase',C('compbl',C('dequote',C('strip',row$code))))
  if(first) {peak<-0;total<-0}
  total<-sx_add(total,C('abs',cx_plus(row$amount,row$expected,TRUE)));peak<-sx_state(C('max',peak,C('abs',cx_plus(row$amount,row$expected,TRUE))))
  if(first && C('n',row$amount,row$expected)<2) emit('grouped_rows',c(list(store(canon,24L),store('FIRST',8L),peak,total),row))
  if(last) {phase<-C('ifc',as.numeric(total>5 || C('n',row$amount,row$expected)<2),'REVIEW','READY');emit('grouped_rows',c(list(store(canon,24L),store(phase,8L),peak,total),row))}
  logs<-c(logs,'group')
 }
 for(record in logs) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
