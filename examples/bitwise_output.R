# DS-070 independent complete-source uint32/67-byte logical record witness.
# No Python plan,helpers or expected values are read. No live-SAS claim.
check <- function(ok, message='outside explicit bitwise67 witness') if(!isTRUE(ok))stop(message)
arity <- c(band=2L,bor=2L,bxor=2L,bnot=1L,blshift=2L,brshift=2L)
ordinary <- function(name) grepl('^[a-z_][a-z0-9_]{0,31}$',name) && !name %in% c(
  '_null_','_n_','_error_','_all_','_numeric_','_character_','_temporary_',
  '_infile_','_file_','_ods_','_page_','_blankpage_')
hex <- function(text)paste(sprintf('%02x',as.integer(charToRaw(text))),collapse='')
uint <- function(value,shift=FALSE) {
  maximum<-if(shift)31 else 4294967295
  check(length(value)==1L && !is.na(value) && is.finite(value) && value>=0 && value<=maximum && value==floor(value))
  if(value==0)0 else value
}
literal <- function(text) {
  check(nchar(text,type='bytes')<=32L && grepl('^[+-]?([0-9]+(\\.[0-9]*)?|\\.[0-9]+)([eE][+-]?[0-9]+)?$',text))
  pieces<-strsplit(text,'[eE]')[[1]];exponent<-if(length(pieces)==2L)as.numeric(pieces[2L]) else 0
  check(is.finite(exponent) && abs(exponent)<=32)
  negative<-startsWith(pieces[1L],'-');base<-sub('^[+-]','',pieces[1L])
  point<-regexpr('.',base,fixed=TRUE)[1L];scale<-(if(point>0L)nchar(base)-point else 0L)-exponent
  digits<-sub('^0+','',gsub('.','',base,fixed=TRUE))
  if(!nzchar(digits))return(0)
  check(!negative)
  if(scale>0) {
    check(scale<nchar(digits))
    check(substr(digits,nchar(digits)-scale+1L,nchar(digits))==strrep('0',scale))
    digits<-substr(digits,1L,nchar(digits)-scale)
  } else if(scale<0) {
    check(nchar(digits)-scale<=10L);digits<-paste0(digits,strrep('0',-scale))
  }
  check(nchar(digits)<=10L);uint(as.numeric(digits))
}
bitwise <- function(name,values) {
  check(name %in% names(arity) && length(values)==arity[[name]])
  first<-uint(values[[1L]]);bits<-floor(first/2^(0:31))%%2
  if(name=='bnot')answer<-1-bits
  else {
    other<-uint(values[[2L]],name %in% c('blshift','brshift'))
    if(name %in% c('blshift','brshift')) {
      if(other==0)answer<-bits
      else if(name=='blshift')answer<-c(rep(0,other),head(bits,32-other))
      else answer<-c(tail(bits,32-other),rep(0,other))
    } else {
      more<-floor(other/2^(0:31))%%2
      answer<-if(name=='band')bits*more else if(name=='bor')pmin(1,bits+more) else (bits+more)%%2
    }
  }
  uint(sum(answer*2^(0:31)))
}
scan <- function(source) {
  chars<-strsplit(source,'',fixed=TRUE)[[1]];at<-1L;line<-1L;first<-NULL;buffer<-'';out<-list();n<-length(chars)
  while(at<=n) {
    ch<-chars[at]
    if(ch=='/' && at<n && chars[at+1L]=='*') {
      at<-at+2L;depth<-1L
      while(at<=n && depth>0L) {
        if(at<n && chars[at]=='/' && chars[at+1L]=='*'){depth<-depth+1L;at<-at+2L}
        else if(at<n && chars[at]=='*' && chars[at+1L]=='/'){depth<-depth-1L;at<-at+2L}
        else {if(chars[at]=='\n')line<-line+1L;at<-at+1L}
      }
      check(depth==0L);buffer<-paste0(buffer,' ');next
    }
    if(!nzchar(trimws(buffer)) && (ch=='*' || ch=='%' && at<n && chars[at+1L]=='*')) {
      while(at<=n && chars[at]!=';'){if(chars[at]=='\n')line<-line+1L;at<-at+1L}
      check(at<=n);at<-at+1L;next
    }
    check(!ch %in% c('"',"'"))
    if(ch==';') {
      text<-gsub('[[:space:]]+',' ',trimws(buffer))
      if(!nzchar(text)){buffer<-'';first<-NULL;at<-at+1L;next}
      check(all(as.integer(charToRaw(text))<128L))
      out[[length(out)+1L]]<-list(text=text,line=first);buffer<-'';first<-NULL;at<-at+1L;next
    }
    if(is.null(first) && !grepl('[[:space:]]',ch))first<-line
    buffer<-paste0(buffer,ch);if(ch=='\n')line<-line+1L;at<-at+1L
  }
  check(!nzchar(trimws(buffer)));out
}
arguments <- function(text) {
  chars<-strsplit(text,'',fixed=TRUE)[[1]];depth<-0L;current<-'';out<-character()
  for(ch in chars) {
    if(ch=='(')depth<-depth+1L
    if(ch==')')depth<-depth-1L
    check(depth>=0L)
    if(ch==',' && depth==0L){check(nzchar(trimws(current)));out<-c(out,current);current<-''}
    else current<-paste0(current,ch)
  }
  check(depth==0L && nzchar(trimws(current)));c(out,current)
}
execute <- function(source) {
  statements<-scan(source);check(length(statements)>=4L && length(statements)<=67L)
  check(tolower(statements[[1L]]$text)=='data _null_' && tolower(tail(statements,1L)[[1L]]$text)=='run')
  check(tolower(statements[[length(statements)-1L]]$text)=='put _all_')
  body<-statements[2:(length(statements)-2L)];check(length(body)>=1L && length(body)<=64L)
  row<-list();spelling<-list();events<-list();nodes<-0L;calls<-0L
  value<-function(text,depth=0L) {
    nodes<<-nodes+1L;check(nodes<=128L && depth<=32L);text<-trimws(text)
    if(grepl('^[+-]?([0-9]+(\\.[0-9]*)?|\\.[0-9]+)([eE][+-]?[0-9]+)?$',text))return(literal(text))
    if(grepl('^[A-Za-z_][A-Za-z0-9_]{0,31}$',text)) {
      name<-tolower(text);check(ordinary(name) && name %in% names(row));return(row[[name]])
    }
    match<-regmatches(text,regexec('^([A-Za-z_][A-Za-z0-9_]{0,31}) *\\((.*)\\)$',text,perl=TRUE))[[1]]
    check(length(match)==3L);name<-tolower(match[2L]);check(name %in% names(arity))
    pieces<-arguments(match[3L]);check(length(pieces)==arity[[name]])
    values<-lapply(pieces,function(piece)value(piece,depth+1L));calls<<-calls+1L
    bitwise(name,values)
  }
  for(statement in body) {
    match<-regmatches(statement$text,regexec('^([A-Za-z_][A-Za-z0-9_]{0,31}) *= *(.*)$',statement$text))[[1]]
    check(length(match)==3L);name<-tolower(match[2L]);check(ordinary(name))
    answer<-value(match[3L]);if(!name %in% names(row))spelling[[name]]<-match[2L]
    row[[name]]<-answer;check(length(row)<=16L)
    events[[length(events)+1L]]<-list(line=statement$line,name=name,value=answer)
  }
  check(calls>=1L)
  pieces<-vapply(names(row),function(name)paste0(spelling[[name]],'=',sprintf('%.0f',uint(row[[name]])),' '),'')
  record<-paste0(paste(pieces,collapse=''),'_ERROR_=0 _N_=1 ');width<-nchar(record,type='bytes');check(width<=67L)
  list(record=record,row=row,spelling=spelling,events=events,output_line=statements[[length(statements)-1L]]$line,
       accounting=c(statements=length(statements),assignments=length(body),bitwise_calls=calls,width=width,variables=length(row)))
}
render <- function(result) {
  out<-paste('ACCOUNT',paste(result$accounting,collapse=' '))
  for(name in names(result$row))out<-c(out,paste('FIELD',hex(result$spelling[[name]]),sprintf('%.0f',result$row[[name]])))
  for(event in result$events)out<-c(out,paste('ASSIGN',event$line,event$name,sprintf('%.0f',event$value)))
  c(out,paste('OUTPUT',result$output_line,hex(result$record)))
}
if(sys.nframe()==0L) {
  paths<-readLines(commandArgs(trailingOnly=TRUE)[1L],warn=FALSE)
  for(i in seq_along(paths)) {
    cat('BEGIN ',i,'\n',sep='')
    answer<-tryCatch(render(execute(paste(readLines(paths[i],warn=FALSE),collapse='\n'))),error=function(e)NULL)
    if(is.null(answer))cat('REFUSED\n') else cat(paste(c('OK',answer),collapse='\n'),'\n',sep='')
    cat('END\n')
  }
}
