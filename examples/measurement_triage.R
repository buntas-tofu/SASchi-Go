here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'composition_wave_oracles.R'))
required<-c("data ranked","set raw","where k>=1","chosen=largest(k,a,b,c)","run","data triage","set ranked","delta=abs(a-b)","total=sum(abs(a),abs(b),abs(c))","rounded=roundz(abs(a-c),0.5)","pick=ifn(flag,coalesce(chosen,0),sum(a,b))","if nmiss(a,b)=0 and delta>=limit then alert=1","else alert=0","if alert or not missing(pick)","put pick","run")

args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
 cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 for(i in seq_len(nrow(cases))) cat(tryCatch(encode(cx_call(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
 text<-paste(readLines(args[2],warn=FALSE),collapse='\n');parts<-trimws(strsplit(text,';',fixed=TRUE)[[1]]);parts<-parts[nzchar(parts)]
 if(!identical(parts,required)) stop('original sequence')
 input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 expected_names<-c('rid','label','code','tag','a','b','c','k','flag','limit','low','high')
 if(!identical(names(input),expected_names)) stop('input schema')
 rows<-lapply(seq_len(nrow(input)),function(i) {
   row<-lapply(input[i,],function(x) if(nzchar(x)) as.numeric(x) else NA_real_)
   row[[2]]<-store(input$label[i],16L);row[[3]]<-store(input$code[i],12L);row[[4]]<-store(input$tag[i],4L);names(row)<-expected_names;row
 })
 cat('STATEMENTS|',length(required),'\n',sep='')
 for(row in rows) emit('raw',row)
 logs<-character()
ranked<-list()
 for(row in rows) {if(!cx_truth(cx_cmp(row$k,1,'ge'))) next;new<-c(row,list(chosen=C('largest',row$k,row$a,row$b,row$c)));ranked[[length(ranked)+1L]]<-new;emit('ranked',new)}
 for(row in ranked) {
 delta<-C('abs',cx_plus(row$a,row$b,TRUE));total<-C('sum',C('abs',row$a),C('abs',row$b),C('abs',row$c));rounded<-C('roundz',C('abs',cx_plus(row$a,row$c,TRUE)),0.5)
 pick<-C('ifn',row$flag,C('coalesce',row$chosen,0),C('sum',row$a,row$b))
 alert<-as.numeric(cx_truth(cx_cmp(C('nmiss',row$a,row$b),0,'eq')) & cx_truth(cx_cmp(delta,row$limit,'ge')))
 if(!(cx_truth(alert) | !cx_truth(C('missing',pick)))) next
 emit('triage',c(row,list(delta,total,rounded,pick,alert)));logs<-c(logs,L(pick))
 }
 for(record in logs) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
