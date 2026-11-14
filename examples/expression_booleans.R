here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'composition_wave_oracles.R'))
required<-c("data booleans","set raw","if (nmiss(a,b)=0 and abs(a-b)<=limit) or not(flag) then accepted=1","else accepted=0","precedence=(a=3 or b=5 and c=5)","neg=(not a=2)","grouped=not(a=2)","missing_truth=not(a)","characters=(upcase(strip(code))='AB12' or missing(strip(label)))","put accepted","run")

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
for(row in rows) {
 a<-row$a;b<-row$b;c<-row$c
 left<-cx_truth(cx_cmp(C('nmiss',a,b),0,'eq')) & cx_truth(cx_cmp(C('abs',cx_plus(a,b,TRUE)),row$limit,'le'))
 accepted<-as.numeric(left | !cx_truth(row$flag))
 precedence<-as.numeric(cx_truth(cx_cmp(a,3,'eq')) | (cx_truth(cx_cmp(b,5,'eq')) & cx_truth(cx_cmp(c,5,'eq'))))
 neg<-cx_cmp(as.numeric(!cx_truth(a)),2,'eq');grouped<-as.numeric(!cx_truth(cx_cmp(a,2,'eq')));missing_truth<-as.numeric(!cx_truth(a))
 characters<-as.numeric(cx_truth(cx_cmp(C('upcase',C('strip',row$code)),'AB12','eq')) | cx_truth(C('missing',C('strip',row$label))))
 emit('booleans',c(row,list(accepted,precedence,neg,grouped,missing_truth,characters)));logs<-c(logs,L(accepted))
}
 for(record in logs) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
