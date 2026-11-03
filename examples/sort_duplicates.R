# Independent complete-source duplicate partition and replacement witness for maintainers.
# Repository/base-R evidence only. No live SAS or physical-layout claim.
script<-sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1L])
examples<-Sys.getenv('SASCHI_EXAMPLES_ROOT',dirname(script))
source(file.path(examples,'character_input.R'))
json<-function(x) {
 if(is.null(x))return('null')
 if(is.list(x)) {
  if(is.null(names(x)))return(paste0('[',paste(vapply(x,json,''),collapse=','),']'))
  return(paste0('{',paste(paste0(vapply(names(x),json,''),':',vapply(x,json,'')),collapse=','),'}'))
 }
 if(length(x)!=1L)return(paste0('[',paste(vapply(as.list(x),json,''),collapse=','),']'))
 if(is.character(x))return(encodeString(x,quote='"',justify='none'))
 if(is.logical(x))return(if(isTRUE(x))'true' else 'false')
 if(is.na(x))return('null')
 sprintf('%.17g',x)
}
compare<-function(a,b,keys,schema) {
 for(key in keys) {
  name<-key$name;x<-a[[name]];y<-b[[name]]
  if(schema[[name]]$type=='character') {
   x<-as.integer(charToRaw(sub(' +$','',x)));y<-as.integer(charToRaw(sub(' +$','',y)))
   width<-max(length(x),length(y));length(x)<-width;length(y)<-width
   x[is.na(x)]<-32L;y[is.na(y)]<-32L;i<-which(x!=y)
   relation<-if(!length(i))0L else if(x[i[1L]]<y[i[1L]])-1L else 1L
  } else relation<-if(is.na(x) && is.na(y))0L else if(is.na(x))-1L else if(is.na(y))1L else if(x<y)-1L else if(x>y)1L else 0L
  if(relation!=0L)return(if(key$descending)-relation else relation)
 }
 0L
}
partition<-function(table,keys,deduplicate) {
 check(length(table$schema)<=32L && length(table$rows)<=1000L)
 check(length(keys)>=1L && length(keys)<=8L && !anyDuplicated(vapply(keys,function(k)k$name,'')))
 check(all(vapply(keys,function(k)k$name %in% names(table$schema),TRUE)))
 # Stable pairwise insertion, with no host order() or Python sort dependency.
 ordinals<-integer()
 for(next_id in seq_along(table$rows)) {
  before<-length(ordinals)+1L
  for(position in seq_along(ordinals))if(compare(table$rows[[next_id]],table$rows[[ordinals[position]]],keys,table$schema)<0L) {before<-position;break}
  ordinals<-append(ordinals,next_id,after=before-1L)
 }
 kept<-removed<-integer()
 for(i in seq_along(ordinals)) {
  if(!deduplicate || i==1L || compare(table$rows[[ordinals[i-1L]]],table$rows[[ordinals[i]]],keys,table$schema)!=0L)kept<-c(kept,ordinals[i])
  else removed<-c(removed,ordinals[i])
 }
 list(table=list(schema=table$schema,rows=table$rows[kept]),removed=list(schema=table$schema,rows=table$rows[removed]),ordered=ordinals,kept=kept,removed_ordinals=removed)
}
by_keys<-function(text,directed) {
 check(startsWith(text,'by '));tokens<-strsplit(substring(text,4L),' ',fixed=TRUE)[[1L]]
 result<-list();at<-1L
 while(at<=length(tokens)) {
  descending<-tokens[at]=='descending'
  if(descending) {check(directed);at<-at+1L;check(at<=length(tokens))}
  name<-tokens[at];check(ordinary(name) && !name %in% c('descending','notsorted'))
  result[[length(result)+1L]]<-list(name=name,descending=descending);at<-at+1L
 }
 check(length(result)>=1L && length(result)<=8L && !anyDuplicated(vapply(result,function(k)k$name,'')))
 result
}
execute_duplicate_source<-function(text) {
 st<-scan_source(text);tables<-list();reports<-list();events<-list();position<-1L;steps<-0L;physical<-observations<-attempts<-outputs<-0L
 title<-NULL;printed<-titled<-duplicates<-0L;sort_destinations<-character()
 event<-function(x)events[[length(events)+1L]]<<-x
 while(position<=length(st)) {
  steps<-steps+1L;check(steps<=64L);normal<-tolower(st[[position]]$text)
  if(startsWith(normal,'data ')) {
   m<-regmatches(normal,regexec('^data ([a-z_][a-z0-9_]{0,31})$',normal))[[1L]]
   check(length(m)==2L && ordinary(m[2L]) && !m[2L] %in% names(tables) && position+4L<=length(st))
   body<-st[position+seq_len(4L)];check(tolower(body[[1L]]$text)=='infile datalines dsd' && tolower(body[[3L]]$text)=='datalines4' && tolower(body[[4L]]$text)=='run')
   schema<-columns(body[[2L]]$text);records<-body[[3L]]$records;check(!is.null(records) && length(records)<=1000L);rows<-list()
   for(card in records) {
    bytes<-as.integer(charToRaw(card));check(length(bytes)<=80L && all(bytes>=32L & bytes<=126L) && !grepl('[\x22\x27]',card))
    fields<-split_fields(card);check(length(fields)==length(schema));row<-list()
    for(i in seq_along(schema)) {
     value<-gsub('^ +| +$','',fields[i]);spec<-schema[[i]]
     if(spec$type=='character') {check(value!='.' && nchar(value,type='bytes')<=spec$length);cell<-paste0(value,strrep(' ',spec$length-nchar(value,type='bytes')))} else cell<-number(value)
     row[[names(schema)[i]]]<-cell
    }
    rows[[length(rows)+1L]]<-row
   }
   for(i in seq_len(length(rows)+1L)) {
    complete<-i<=length(rows);event(list(kind='character_input',line=body[[2L]]$line,attempt=i,complete=complete))
    if(complete)event(list(kind='character_output',line=body[[2L]]$line,observation=i))
   }
   tables[[m[2L]]]<-list(schema=schema,rows=rows);physical<-physical+length(records);observations<-observations+length(rows);attempts<-attempts+length(rows)+1L;outputs<-outputs+length(rows)
   position<-position+5L
  } else if(startsWith(normal,'proc sort ')) {
   check(position+2L<=length(st) && tolower(st[[position+2L]]$text)=='run')
   m<-regmatches(normal,regexec('^proc sort data=([a-z_][a-z0-9_]{0,31})( out=([a-z_][a-z0-9_]{0,31}))? dupout=([a-z_][a-z0-9_]{0,31}) nodupkey$',normal))[[1L]]
   special<-length(m)>0L
   if(special) {
    input<-m[2L];replace<-!nzchar(m[4L]);output<-if(replace)input else m[4L];duplicate<-m[5L];dedup<-TRUE
    check(ordinary(duplicate) && !duplicate %in% names(tables) && duplicate!=output && duplicate!=input)
    if(replace)check(input %in% sort_destinations) else check(!output %in% names(tables))
    duplicates<-duplicates+1L
   } else {
    m<-regmatches(normal,regexec('^proc sort data=([a-z_][a-z0-9_]{0,31}) out=([a-z_][a-z0-9_]{0,31})( nodupkey)?$',normal))[[1L]]
    check(length(m)>0L);input<-m[2L];output<-m[3L];dedup<-nzchar(m[4L]);check(!output %in% names(tables))
   }
   check(ordinary(input) && input %in% names(tables) && ordinary(output))
   keys<-by_keys(tolower(st[[position+1L]]$text),!special);answer<-partition(tables[[input]],keys,dedup)
   tables[[output]]<-answer$table;sort_destinations<-unique(c(sort_destinations,output))
   if(special) {
    tables[[duplicate]]<-answer$removed
    event(list(event='sort_dupout',line=st[[position]]$line,source=input,destination=output,duplicate_destination=duplicate,replace=replace,source_ordinals=as.list(answer$ordered),kept_ordinals=as.list(answer$kept),removed_ordinals=as.list(answer$removed_ordinals)))
   } else event(list(event='sort',line=st[[position]]$line,source=input,destination=output,source_ordinals=as.list(answer$ordered),kept_ordinals=as.list(answer$kept)))
   position<-position+3L
  } else if(normal=='title' || startsWith(normal,'title ')) {
   title<-NULL
   if(normal!='title') {
    literal<-substring(st[[position]]$text,7L);quote<-substr(literal,1L,1L)
    check(quote %in% c('"',"'") && substr(literal,nchar(literal),nchar(literal))==quote)
    title<-substr(literal,2L,nchar(literal)-1L);check(nchar(title)>=1L && nchar(title)<=128L && nzchar(trimws(title)) && !grepl('[%&]',title))
   }
   titled<-titled+1L;check(titled<=32L);event(if(is.null(title))'title|reset' else paste0('title|set|',hex(title)));position<-position+1L
  } else if(startsWith(normal,'proc print ')) {
   m<-regmatches(normal,regexec('^proc print data=([a-z_][a-z0-9_]{0,31})$',normal))[[1L]]
   check(length(m)==2L && m[2L] %in% names(tables) && position<length(st) && tolower(st[[position+1L]]$text)=='run')
   printed<-printed+1L;check(printed<=3L);table<-tables[[m[2L]]];records<-if(is.null(title))character() else paste0('TITLE: ',title)
   header<-paste('obs',paste(names(table$schema),collapse=' '));records<-c(records,header)
   event(paste('mixed-print','input',m[2L],length(table$rows),sep='|'))
   if(!is.null(title))event(paste0('mixed-print|title|',hex(records[1L])))
   event(paste0('mixed-print|header|',hex(header)))
   for(i in seq_along(table$rows)) {
    row<-table$rows[[i]];fields<-vapply(names(table$schema),function(name) {
     if(table$schema[[name]]$type=='character')json(sub(' +$','',row[[name]])) else {
      x<-row[[name]];check(is.na(x) || x==trunc(x));if(is.na(x))'.' else if(x==0)'0' else sprintf('%.0f',x)
     }
    },'')
    line<-paste(i,paste(fields,collapse=' '));check(nchar(line,type='bytes')<=415L);records<-c(records,line);event(paste0('mixed-print|row|',hex(line)))
   }
   content<-paste0(paste(records,collapse='\n'),'\n');check(nchar(header,type='bytes')<=1055L && nchar(content,type='bytes')<=417056L)
   name<-sprintf('print_%02d.txt',printed);reports[[name]]<-content;event(paste('mixed-print','output',name,nchar(content,type='bytes'),sep='|'));position<-position+2L
  } else stop('unowned statement')
 }
 check(duplicates>0L)
 list(tables=tables,reports=reports,events=events,accounting=c(statements=length(st),physical_records=physical,observations=observations,attempts=attempts,outputs=outputs))
}
paths<-readLines(commandArgs(trailingOnly=TRUE)[1L],warn=FALSE)
for(i in seq_along(paths)) {
 cat('BEGIN ',i,'\n',sep='')
 answer<-tryCatch(execute_duplicate_source(paste(readLines(paths[i],warn=FALSE),collapse='\n')),error=function(e)NULL)
 if(is.null(answer))cat('REFUSED\n') else {
  cat(paste(c('OK',render(answer)),collapse='\n'),'\n',sep='')
  for(name in names(answer$reports))cat('REPORT ',name,' ',hex(answer$reports[[name]]),'\n',sep='')
  for(item in answer$events)cat('EVENT ',json(item),'\n',sep='')
 }
 cat('END\n')
}
