here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'composition_wave_oracles.R'))
required<-c("data source_filtered","set raw","where flag or not missing(a)","run","data eligible","set source_filtered","canon=upcase(compbl(strip(dequote(label))))","identifier=cats(substrn(upcase(strip(code)),1,4),'-',propcase(strip(label),' -'))","bad=notalnum(strip(code))","score=sum(abs(a),abs(b))","status=ifc(bad=0 and score>=limit,'OK','REVIEW')","if status='OK'","put identifier","put score","run")

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
selected<-Filter(function(row) cx_truth(row$flag) | !cx_truth(C('missing',row$a)),rows)
 for(row in selected) emit('source_filtered',row)
 for(row in selected) {
 canon<-C('upcase',C('compbl',C('strip',C('dequote',row$label))))
 identifier<-C('cats',C('substrn',C('upcase',C('strip',row$code)),1,4),'-',C('propcase',C('strip',row$label),' -'))
 bad<-C('notalnum',C('strip',row$code));score<-C('sum',C('abs',row$a),C('abs',row$b))
 test<-as.numeric(cx_truth(cx_cmp(bad,0,'eq')) & cx_truth(cx_cmp(score,row$limit,'ge')))
 status<-C('ifc',test,'OK','REVIEW');if(!cx_truth(cx_cmp(status,'OK','eq'))) next
 emit('eligible',c(row,list(store(canon,16L),store(identifier,200L),bad,score,store(status,200L))));logs<-c(logs,T(identifier),L(score))
 }
 for(record in logs) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
