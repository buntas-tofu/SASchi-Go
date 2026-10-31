# DS-058/059 independent complete-source input/state witness for maintainers.
# Repository/base-R evidence, not live SAS or general CSV.
args<-commandArgs(trailingOnly=TRUE)
self<-sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1]);here<-dirname(normalizePath(self))
# Reuse the earlier independent exact-decimal and opaque-source scanner. No
# Python parser, plan, decoder or result is read by this R implementation.
prior<-readLines(file.path(here,'input_list.R'),warn=FALSE)
cut<-grep('^program <- function',prior)[1]
eval(parse(text=prior[seq_len(cut-1)]))
source(file.path(here,'input_ranges.R'))

read_numeric <- function(records,width,delimiter,firstobs) {
  if(width<1||width>32||length(records)>10000||firstobs<1||firstobs>10001) stop('input bounds')
  for(record in records) {
    bytes<-as.integer(charToRaw(record))
    if(length(bytes)>80||any(bytes<32|bytes>126)||grepl(';',record,fixed=TRUE)) stop('physical record')
  }
  rows<-list();pending<-numeric()
  if(firstobs>length(records)) return(rows)
  for(record in records[seq.int(firstobs,length(records))]) {
    if(!nzchar(trimws(record,whitespace=' '))) next
    fields<-strsplit(paste0(record,delimiter,'END'),delimiter,fixed=TRUE)[[1]]
    fields<-head(fields,-1)
    for(field in fields) {
      if(!nzchar(field)) next
      token<-if(delimiter==',') trimws(field,whitespace=' ') else field
      if(!nzchar(token)) stop('conservative blank field refusal')
      pending<-c(pending,number(token))
      if(length(pending)==width) {rows[[length(rows)+1L]]<-pending;pending<-numeric();break}
    }
  }
  rows
}
infile_options <- function(text) {
  rest<-capture('infile\\s+(?:cards|datalines)\\s+(.+)',text)
  if(is.null(rest)) stop('inline source only')
  options<-list()
  while(nzchar(rest)) {
    m<-regmatches(rest,regexec('^(?:(dlm)\\s*=\\s*([\x27\"]),\\2|(firstobs)\\s*=\\s*([1-9][0-9]{0,4}))(?=\\s|$)',rest,perl=TRUE,ignore.case=TRUE))[[1]]
    if(!length(m)) stop('INFILE options')
    key<-tolower(if(nzchar(m[2])) m[2] else m[4])
    if(!is.null(options[[key]])) stop('duplicate INFILE option')
    options[[key]]<-if(key=='dlm') ',' else as.integer(m[5])
    rest<-trimws(substring(rest,nchar(m[1])+1))
  }
  if(is.null(options$dlm)) stop('comma DLM required')
  first<-if(is.null(options$firstobs)) 1L else options$firstobs
  if(first>10001) stop('FIRSTOBS bound')
  list(delimiter=',',firstobs=first)
}
normalize_code <- function(text) {
  chars<-strsplit(text,'',fixed=TRUE)[[1]];quote<-'';out<-'';i<-1L
  while(i<=length(chars)) {
    ch<-chars[i];nextch<-if(i<length(chars)) chars[i+1L] else ''
    if(nzchar(quote)) {
      out<-paste0(out,ch)
      if(ch==quote) {
        if(nextch==quote) {out<-paste0(out,nextch);i<-i+1L} else quote<-''
      }
    } else if(ch %in% c("'",'"')) {quote<-ch;out<-paste0(out,ch)}
    else if(grepl('[[:space:]]',ch)) {
      if(!endsWith(out,' ')) out<-paste0(out,' ')
    } else out<-paste0(out,ch)
    i<-i+1L
  }
  trimws(out)
}
put_literals <- function(text) {
  pattern<-"(?:\"(?:[^\"]|\"\")*\"|'(?:[^']|'')*')"
  if(!grepl(paste0('^(?:',pattern,'\\s*)+$'),text,perl=TRUE)) stop('literal PUT')
  tokens<-regmatches(text,gregexpr(pattern,text,perl=TRUE))[[1]]
  values<-vapply(tokens,function(token) {
    quote<-substr(token,1,1);body<-substr(token,2,nchar(token)-1)
    if(quote=='"'&&grepl('[&%]',body)) stop('macro literal')
    if(!nzchar(body)) return(quote)
    value<-gsub(paste0(quote,quote),quote,body,fixed=TRUE)
    bytes<-as.integer(charToRaw(value));if(any(bytes<32|bytes>126)) stop('literal bytes')
    value
  },'')
  record<-paste(values,collapse='');if(nchar(record,type='bytes')>64) stop('literal columns')
  record
}
program <- function(path) {
  parsed<-scan_program(path);statements<-parsed$statements;at<-1L
  cat('STATEMENTS:',length(statements),'\n',sep='')
  ordinary<-function(name) grepl('^[a-z_][a-z0-9_]{0,31}$',name,perl=TRUE)&&!(name %in% c('_n_','_error_','_all_','_numeric_','_character_','_infile_','_file_','_ods_','_page_','_blankpage_'))
  while(at<=length(statements)) {
    header<-capture('data\\s+([a-z_][a-z0-9_]{0,31})(?:\\s*\\(\\s*(keep|drop)\\s*=\\s*(.*?)\\s*\\))?',statements[at]);at<-at+1L
    if(is.null(header)) stop('DATA required')
    destination<-tolower(header[1]);selection<-if(length(header)>1&&nzchar(header[2])) list(mode=tolower(header[2]),names=expand_names(header[3])$names) else NULL
    schema<-character();retained<-list();body<-list();input<-NULL;records<-NULL;explicit<-FALSE;options<-NULL;newrange<-FALSE
    add<-function(name) {
      if(name=='_n_') return(invisible(NULL))
      if(!ordinary(name)) stop('ordinary scalar name')
      if(!(name %in% schema)) schema<<-c(schema,name)
    }
    expression<-function(text) {
      text<-tolower(trimws(text))
      if(text=='_n_') return(list(kind='atom',value=text))
      if(grepl('^[a-z_][a-z0-9_]{0,31}$',text,perl=TRUE)) {add(text);return(list(kind='atom',value=text))}
      call<-capture('(sum|min|max|int)\\s*\\((.*)\\)',text)
      if(!is.null(call)) {
        terms<-strsplit(call[2],',',fixed=TRUE)[[1]]
        if(!length(terms)||length(terms)>32||call[1]=='int'&&length(terms)!=1) stop('arity')
        return(list(kind=call[1],args=lapply(terms,expression)))
      }
      number(text);list(kind='atom',value=text)
    }
    predicate<-function(text) {
      m<-capture('(.+?)\\s*(<=|>=|\\^=|~=|<>|=|<|>|\\beq\\b|\\bne\\b|\\blt\\b|\\bgt\\b|\\ble\\b|\\bge\\b)\\s*(.+)',text)
      if(is.null(m)) return(list(op='truth',left=expression(text)))
      list(op=tolower(m[2]),left=expression(m[1]),right=expression(m[3]))
    }
    parse_action<-function(text) {
      test<-capture('if\\s+(.+?)\\s+then\\s+(.+)',text)
      if(!is.null(test)) return(list(kind='if',condition=predicate(test[1]),body=parse_action(test[2])))
      subset<-capture('if\\s+(.+)',text)
      if(!is.null(subset)) return(list(kind='subset',condition=predicate(subset[1])))
      out<-capture('output(?:\\s+([a-z_][a-z0-9_]{0,31}))?',text)
      if(!is.null(out)) {
        if(length(out)&&nzchar(out)&&tolower(out)!=destination) stop('OUTPUT target')
        explicit<<-TRUE;return(list(kind='output'))
      }
      lit<-capture('put\\s+(.+)',text)
      if(!is.null(lit)&&substr(lit,1,1) %in% c("'",'"')) return(list(kind='literal',value=put_literals(lit)))
      named<-capture('put\\s+((?:[a-z_][a-z0-9_]{0,31}\\s*=\\s*)+)',text)
      if(!is.null(named)) {
        names<-tolower(strsplit(trimws(named),'\\s*=\\s*',perl=TRUE)[[1]]);names<-names[nzchar(names)]
        for(name in names) add(name)
        return(list(kind='put',names=names))
      }
      assign<-capture('([a-z_][a-z0-9_]{0,31})\\s*(=|\\+)\\s*(.+)',text)
      if(!is.null(assign)) {
        name<-tolower(assign[1]);add(name);value<-expression(assign[3])
        if(assign[2]=='+'&&is.null(retained[[name]])) retained[[name]]<<-0
        return(list(kind=if(assign[2]=='+')'sum' else 'assign',name=name,value=value))
      }
      stop('unhandled scalar action')
    }
    while(at<=length(statements)) {
      text<-normalize_code(statements[at]);position<-at;at<-at+1L
      if(tolower(text) %in% c('cards','datalines')) {records<-parsed$records[[as.character(position)]];break}
      if(grepl('^infile\\b',text,ignore.case=TRUE,perl=TRUE)) {
        if(!is.null(options)||!is.null(input)||length(body)) stop('INFILE position')
        options<-infile_options(text);next
      }
      keep<-capture('retain\\s+([a-z_][a-z0-9_]{0,31})\\s+(.+)',text)
      read<-capture('input\\s+(.+)',text)
      project<-capture('(keep|drop)\\s+(.+)',text)
      if(!is.null(keep)) {name<-tolower(keep[1]);add(name);retained[[name]]<-number(trimws(keep[2]))}
      else if(!is.null(read)) {
        if(!is.null(input)||length(body)) stop('INPUT position')
        expanded<-expand_names(read);input<-expanded$names;newrange<-expanded$range
        for(name in input) add(name)
      } else if(!is.null(project)) {
        if(!is.null(selection)) stop('one output projection')
        selection<-list(mode=tolower(project[1]),names=expand_names(project[2])$names)
      } else if(grepl('^else\\b',text,ignore.case=TRUE,perl=TRUE)) {
        if(!length(body)||body[[length(body)]]$kind!='if'||!is.null(body[[length(body)]]$otherwise)) stop('ELSE ownership')
        body[[length(body)]]$otherwise<-parse_action(sub('(?i)^else\\s+','',text,perl=TRUE))
      } else body[[length(body)+1L]]<-parse_action(text)
    }
    if(is.null(input)||is.null(records)||at>length(statements)||tolower(statements[at])!='run'||is.null(options)&&!newrange) stop('complete new-profile input step')
    at<-at+1L
    selected<-schema
    if(!is.null(selection)) {
      if(any(!(selection$names %in% schema))) stop('unknown projected name')
      selected<-schema[(schema %in% selection$names)==(selection$mode=='keep')]
      if(!length(selected)) stop('empty projection')
    }
    decoded<-read_numeric(records,length(input),if(is.null(options))' ' else options$delimiter,if(is.null(options))1L else options$firstobs)
    saved<-retained;output<-list();logs<-character()
    value<-function(e) {
      if(e$kind=='atom') return(if(e$value %in% names(row)) row[[e$value]] else number(e$value))
      values<-vapply(e$args,value,0.0)
      if(e$kind=='int') return(if(is.na(values)) NA_real_ else trunc(values))
      if(all(is.na(values))) return(NA_real_)
      switch(e$kind,sum=sum(values,na.rm=TRUE),min=min(values,na.rm=TRUE),max=max(values,na.rm=TRUE),stop('function'))
    }
    test<-function(t) {
      a<-value(t$left);if(t$op=='truth') return(!is.na(a)&&a!=0)
      b<-value(t$right);if(is.na(a)) a<- -Inf;if(is.na(b)) b<- -Inf
      switch(t$op,'='=a==b,eq=a==b,'^='=a!=b,'~='=a!=b,'<>'=a!=b,ne=a!=b,'<'=a<b,lt=a<b,'>'=a>b,gt=a>b,'<='=a<=b,le=a<=b,'>='=a>=b,ge=a>=b,stop('predicate'))
    }
    perform<-function(op) {
      if(op$kind=='if') {
        if(test(op$condition)) return(perform(op$body))
        if(!is.null(op$otherwise)) return(perform(op$otherwise))
      } else if(op$kind=='subset') return(test(op$condition))
      else if(op$kind=='assign') row[[op$name]]<<-value(op$value)
      else if(op$kind=='sum') row[[op$name]]<<-sum(c(row[[op$name]],value(op$value)),na.rm=TRUE)
      else if(op$kind=='output') output[[length(output)+1L]]<<-row[selected]
      else if(op$kind=='literal') logs<<-c(logs,op$value)
      else if(op$kind=='put') logs<<-c(logs,paste(vapply(op$names,function(n)paste0(n,'=',render(row[[n]])),''),collapse=' '))
      else stop('execution')
      TRUE
    }
    for(index in seq_along(decoded)) {
      row<-setNames(as.list(rep(NA_real_,length(schema))),schema)
      row[names(saved)]<-saved;row[input]<-as.list(decoded[[index]]);row[['_n_']]<-as.numeric(index);alive<-TRUE
      for(op in body) if(!perform(op)) {alive<-FALSE;break}
      saved<-row[names(retained)]
      if(alive&&!explicit) output[[length(output)+1L]]<-row[selected]
    }
    cat('STEP:',destination,'\n','SCHEMA:',paste(selected,collapse=','),'\n','READS:',length(decoded),'\n',sep='')
    if(destination!='_null_') for(r in output) cat('ROW:',encoded_rows(list(r)),'\n',sep='')
    for(log in logs) cat('LOG:',hex(log),'\n',sep='')
  }
}
if(args[1]=='program') program(args[2]) else if(args[1]=='batch') {
  files<-readLines(args[2],warn=FALSE)
  for(i in seq_along(files)) {
    cat('CASE:',i,'\n',sep='')
    answer<-tryCatch(list(ok=TRUE,lines=capture.output(program(files[i]))),error=function(e)list(ok=FALSE,lines=character()))
    if(answer$ok) for(line in answer$lines) cat(line,'\n',sep='')
    cat('ANSWER:',if(answer$ok)'OK' else 'REFUSE','\n',sep='')
  }
} else stop('mode')
