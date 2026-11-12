# Independent whole-program character operations using base-R primitives.
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
encode<-function(x) if(is.character(x)) paste0('c:',hex(x)) else if(is.na(x)) 'm:' else paste0('n:',sprintf('%.17g',x))
emit<-function(name,row) cat(paste(c('ROW',name,vapply(row,encode,'')),collapse='|'),'\n',sep='')
store<-function(x,w) paste0(substr(x,1,w),strrep(' ',max(0,w-nchar(x,type='bytes'))))
upper_ascii<-function(x) chartr('abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ',x)
lower_ascii<-function(x) chartr('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz',x)
position<-function(x,needle) {p<-as.integer(regexpr(needle,x,fixed=TRUE)[1]);if(p<0) 0 else p}
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  invisible(NULL)
  # Composition acceptance is whole-program evidence, not additional scalar pins.
} else if(args[1]=='program') {
  source<-gsub('(?s)/\\*.*?\\*/','',paste(readLines(args[2],warn=FALSE),collapse='\n'),perl=TRUE)
  statements<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);statements<-statements[nzchar(statements)]
  required<-c('data prepared','set raw','upper=upcase(text)','lower=lowcase(text)',"first=scan(upper,1,'|')","last=scan(upper,-1,'|')","words=countw(upper,'|')","at=index(upper,'AB')","found=find(upper,'ab','I')",'tight=compress(first)',"mapped=translate(tight,'12','AB')","replaced=tranwrd(mapped,'12','XY')",'blank=missing(backup)','gaps=cmiss(backup,n)',"chosen=coalescec(backup,replaced,'NA')",'output','put chosen','run')
  if(!identical(statements,required)) stop('original sequence')
  input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
  rows<-lapply(seq_len(nrow(input)),function(i) list(store(input$text[i],8L),store(input$backup[i],4L),if(nzchar(input$n[i])) as.numeric(input$n[i]) else NA_real_))
  cat('STATEMENTS|',length(statements),'\n',sep='');for(row in rows) emit('raw',row)
  records<-character()
  for(row in rows) {
    text<-row[[1]];backup<-row[[2]];n<-row[[3]]
    upper<-upper_ascii(text);lower<-lower_ascii(text)
    parts<-strsplit(upper,'|',fixed=TRUE)[[1]];parts<-parts[nzchar(parts)]
    first<-store(if(length(parts)) parts[1] else ' ',8L);last<-store(if(length(parts)) parts[length(parts)] else ' ',8L)
    tight<-store(gsub(' ','',first,fixed=TRUE),8L);mapped<-chartr('AB','12',tight);replaced<-store(gsub('12','XY',mapped,fixed=TRUE),200L)
    blank<-!nzchar(gsub(' ','',backup,fixed=TRUE));gaps<-as.numeric(blank)+as.numeric(is.na(n))
    chosen<-if(!blank) backup else if(nzchar(gsub(' ','',replaced,fixed=TRUE))) replaced else 'NA'
    chosen<-store(chosen,200L)
    emit('prepared',c(row,list(upper,lower,first,last,length(parts),position(upper,'AB'),position(upper,'AB'),tight,mapped,replaced,as.numeric(blank),gaps,chosen)))
    records<-c(records,paste0(trimws(chosen,whitespace=' '),' '))
  }
  for(record in records) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
