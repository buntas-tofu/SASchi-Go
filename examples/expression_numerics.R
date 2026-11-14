here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'composition_wave_oracles.R'))
required<-c("data num_trees","set raw","delta=abs(a-b)","score=sum(abs(a),abs(b),largest(k,a,b,c))","rounded=roundz(abs(a-c),0.5)","coalesced=coalesce(smallest(k,a,b,c),0)","balance=sum(a,b)-sum(b,c)","nmissing=nmiss(abs(a),abs(b))","tie=roundz(abs(-2.5),1)","put score","run")

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
 a<-row$a;b<-row$b;c<-row$c;k<-row$k
 delta<-C('abs',cx_plus(a,b,TRUE));score<-C('sum',C('abs',a),C('abs',b),C('largest',k,a,b,c))
 rounded<-C('roundz',C('abs',cx_plus(a,c,TRUE)),0.5);coalesced<-C('coalesce',C('smallest',k,a,b,c),0)
 balance<-cx_plus(C('sum',a,b),C('sum',b,c),TRUE);nmissing<-C('nmiss',C('abs',a),C('abs',b));tie<-C('roundz',C('abs',-2.5),1)
 emit('num_trees',c(row,list(delta,score,rounded,coalesced,balance,nmissing,tie)));logs<-c(logs,L(score))
}
 for(record in logs) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
