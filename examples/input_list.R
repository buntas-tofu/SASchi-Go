# DS-044 independent decimal factorization, record cursor and program witness.
# Repository/base-R evidence for maintainers; no live SAS.
hex <- function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
unhex <- function(x) {
  if(!nzchar(x)) return('')
  rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))
}
capture <- function(pattern,text) {
  m<-regmatches(text,regexec(paste0('(?i)^',pattern,'$'),text,perl=TRUE))[[1]]
  if(length(m)) m[-1] else NULL
}
number <- function(token) {
  if(nchar(token,type='bytes')<1 || nchar(token,type='bytes')>32) stop('token width')
  if(token=='.') return(NA_real_)
  if(!grepl('^[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?$',token,perl=TRUE)) stop('numeric syntax')
  pieces<-strsplit(tolower(token),'e',fixed=TRUE)[[1]]
  mantissa<-gsub('^[+-]','',pieces[1]);digits<-gsub('.','',mantissa,fixed=TRUE)
  exponent<-if(length(pieces)==2) as.numeric(pieces[2]) else 0
  if(nchar(digits)>15 || abs(exponent)>15) stop('digit/exponent bound')
  dot<-regexpr('.',mantissa,fixed=TRUE)[1]
  scale<-(if(dot>0) nchar(mantissa)-dot else 0)-exponent
  coefficient<-as.numeric(digits)
  # All coefficients below10^15 are exact binary integers. For a decimal
  # denominator10^scale, remove every factor5 or refuse a rounded value.
  if(coefficient!=0 && scale>0) for(k in seq_len(scale)) {
    if(coefficient%%5!=0) stop('rounded decimal')
    coefficient<-coefficient/5
  }
  value<-if(scale>0) coefficient/(2^scale) else coefficient*(10^(-scale))
  if(substr(token,1,1)=='-') value<- -value
  if(!is.finite(value) || abs(value)>2147483647) stop('range')
  if(value==0) 0 else value
}
read_records <- function(records,width) {
  if(width<1 || width>32 || width!=trunc(width) || length(records)>10000) stop('bounds')
  for(record in records) {
    bytes<-as.integer(charToRaw(record))
    if(length(bytes)>80 || any(bytes<32 | bytes>126) || grepl(';',record,fixed=TRUE)) stop('record')
  }
  rows<-list(); cursor<-1L
  while(cursor<=length(records)) {
    observation<-numeric()
    while(length(observation)<width && cursor<=length(records)) {
      fields<-strsplit(records[cursor],' +',perl=TRUE)[[1]];fields<-fields[nzchar(fields)]
      needed<-width-length(observation)
      if(length(fields)) observation<-c(observation,vapply(head(fields,needed),number,0.0))
      cursor<-cursor+1L
    }
    if(length(observation)==width) rows[[length(rows)+1L]]<-unname(observation)
  }
  rows
}
render <- function(x) if(is.na(x)) '.' else sprintf('%.17g',x)
encoded_rows <- function(rows) paste(vapply(rows,function(row) paste(vapply(row,render,''),collapse=','),''),collapse='|')

# This scanner consumes the entire source independently, never importing a
# Python plan or copying corpus source. Inline records bypass code scanning.
scan_program <- function(path) {
  lines<-readLines(path,warn=FALSE);code<-paste(lines,collapse='\n')
  chars<-strsplit(code,'',fixed=TRUE)[[1]];i<-1L;n<-length(chars)
  statements<-character();buffer<-'';quote<-'';comment<-FALSE;records<-list()
  while(i<=n) {
    ch<-chars[i];nextch<-if(i<n) chars[i+1L] else ''
    if(comment) {
      if(ch=='*' && nextch=='/') {comment<-FALSE;i<-i+2L;buffer<-paste0(buffer,' ')} else i<-i+1L
      next
    }
    if(nzchar(quote)) {
      buffer<-paste0(buffer,ch)
      if(ch==quote) {
        if(nextch==quote) {buffer<-paste0(buffer,nextch);i<-i+1L} else quote<-''
      }
      i<-i+1L;next
    }
    if(ch=='/' && nextch=='*') {comment<-TRUE;i<-i+2L;next}
    if(ch %in% c("'",'"')) {quote<-ch;buffer<-paste0(buffer,ch);i<-i+1L;next}
    if(ch!=';') {buffer<-paste0(buffer,ch);i<-i+1L;next}
    statement<-trimws(buffer);buffer<-'';i<-i+1L
    if(!nzchar(statement)) stop('unexpected null code statement')
    statements<-c(statements,statement)
    if(tolower(statement) %in% c('cards','datalines')) {
      tail<-paste(chars[i:n],collapse='');physical<-strsplit(paste0(tail,'\nEND'),'\n',fixed=TRUE)[[1]]
      if(nzchar(trimws(physical[1],whitespace=' '))) stop('inline header')
      end<-which(grepl('^ *; *$',physical))
      if(!length(end)) stop('inline terminator')
      end<-end[1];records[[as.character(length(statements))]]<-if(end>2) physical[2:(end-1)] else character()
      consumed<-sum(nchar(physical[seq_len(end)],type='chars'))+end
      i<-i+consumed
    }
  }
  if(comment || nzchar(quote) || nzchar(trimws(buffer))) stop('unconsumed source')
  list(statements=statements,records=records)
}
program <- function(path) {
  parsed<-scan_program(path);statements<-parsed$statements;at<-1L
  cat('STATEMENTS:',length(statements),'\n',sep='')
  while(at<=length(statements)) {
    header<-capture('data\\s+([a-z_]\\w*)',statements[at]);at<-at+1L
    if(is.null(header)) stop('DATA required')
    schema<-character();retained<-list();body<-list();input<-NULL;records<-NULL;explicit<-FALSE
    add<-function(name) {if(!(name %in% c(schema,'_n_'))) schema<<-c(schema,name)}
    discover_atom<-function(text) {
      if(grepl('^[a-z_]\\w*$',text,perl=TRUE)) add(tolower(text)) else number(text)
    }
    parse_action<-function(text) {
      test<-capture('if\\s+([a-z_]\\w*|[0-9.]+)\\s*(<=|>=|\\^=|~=|=|<|>|eq|ne|lt|gt|le|ge)\\s*([a-z_]\\w*|[0-9.]+)\\s+then\\s+(.+)',text)
      if(!is.null(test)) {
        discover_atom(test[1]);discover_atom(test[3])
        return(list(kind='if',left=tolower(test[1]),op=tolower(test[2]),right=tolower(test[3]),body=parse_action(test[4])))
      }
      if(tolower(text)=='output') {explicit<<-TRUE;return(list(kind='output'))}
      lit<-capture('put\\s+("[^";]*"|\x27[^\x27;]*\x27)',text)
      if(!is.null(lit)) return(list(kind='literal',value=substr(lit,2,nchar(lit)-1)))
      named<-capture('put\\s+((?:[a-z_]\\w*\\s*=\\s*)+)',text)
      if(!is.null(named)) {
        names<-tolower(strsplit(trimws(named),'\\s*=\\s*',perl=TRUE)[[1]]);names<-names[nzchar(names)]
        for(name in names) add(name)
        return(list(kind='put',names=names))
      }
      assign<-capture('([a-z_]\\w*)\\s*(=|\\+)\\s*([a-z_]\\w*|[+-]?[0-9.]+)',text)
      if(!is.null(assign)) {
        name<-tolower(assign[1]);add(name);discover_atom(assign[3])
        if(assign[2]=='+' && is.null(retained[[name]])) retained[[name]]<<-0
        return(list(kind=if(assign[2]=='+') 'sum' else 'assign',name=name,value=tolower(assign[3])))
      }
      stop('unhandled action')
    }
    while(at<=length(statements)) {
      text<-statements[at];position<-at;at<-at+1L
      if(tolower(text) %in% c('cards','datalines')) {records<-parsed$records[[as.character(position)]];break}
      keep<-capture('retain\\s+([a-z_]\\w*)\\s+([+-]?[0-9.]+)',text)
      read<-capture('input\\s+([a-z_]\\w*(?:\\s+[a-z_]\\w*)*)',text)
      if(!is.null(keep)) {name<-tolower(keep[1]);add(name);retained[[name]]<-number(keep[2])}
      else if(!is.null(read)) {
        if(!is.null(input) || length(body)) stop('input position')
        input<-tolower(strsplit(read,'\\s+',perl=TRUE)[[1]])
        if(anyDuplicated(input)) stop('input duplicate')
        for(name in input) add(name)
      } else body[[length(body)+1L]]<-parse_action(text)
    }
    if(is.null(input) || is.null(records) || at>length(statements) || tolower(statements[at])!='run') stop('complete input step required')
    at<-at+1L;rows<-read_records(records,length(input));saved<-retained;output<-list();logs<-character()
    atom<-function(text) if(text %in% names(row)) row[[text]] else number(text)
    perform<-function(op) {
      if(op$kind=='if') {
        a<-atom(op$left);b<-atom(op$right);if(is.na(a)) a<- -Inf;if(is.na(b)) b<- -Inf
        yes<-switch(op$op,'='=a==b,eq=a==b,'^='=a!=b,'~='=a!=b,ne=a!=b,'<'=a<b,lt=a<b,'>'=a>b,gt=a>b,'<='=a<=b,le=a<=b,'>='=a>=b,ge=a>=b,stop('predicate'))
        if(yes) perform(op$body)
      } else if(op$kind=='assign') row[[op$name]]<<-atom(op$value)
      else if(op$kind=='sum') row[[op$name]]<<-sum(c(row[[op$name]],atom(op$value)),na.rm=TRUE)
      else if(op$kind=='output') output[[length(output)+1L]]<<-row[schema]
      else if(op$kind=='literal') logs<<-c(logs,op$value)
      else if(op$kind=='put') logs<<-c(logs,paste(vapply(op$names,function(n) paste0(n,'=',render(row[[n]])),''),collapse=' '))
      else stop('execution')
    }
    for(index in seq_along(rows)) {
      row<-setNames(as.list(rep(NA_real_,length(schema))),schema)
      row[names(saved)]<-saved;row[input]<-as.list(rows[[index]]);row[['_n_']]<-as.numeric(index)
      for(op in body) perform(op)
      saved<-row[names(retained)]
      if(!explicit) output[[length(output)+1L]]<-row[schema]
    }
    cat('STEP:',tolower(header),'\n','SCHEMA:',paste(schema,collapse=','),'\n','READS:',length(rows),'\n',sep='')
    if(tolower(header)!='_null_') for(r in output) cat('ROW:',encoded_rows(list(r)),'\n',sep='')
    for(log in logs) cat('LOG:',hex(log),'\n',sep='')
  }
}
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE)
  for(i in seq_len(nrow(cases))) {
    r<-cases[i,];n<-as.integer(r$count)
    records<-if(n) vapply(strsplit(paste0(r$records,':END'),':',fixed=TRUE)[[1]][seq_len(n)],unhex,'') else character()
    answer<-tryCatch(paste0('OK:',encoded_rows(read_records(records,as.integer(r$width)))),error=function(e) 'REFUSE')
    cat(answer,'\n',sep='')
  }
} else if(args[1]=='program') program(args[2]) else stop('mode')
