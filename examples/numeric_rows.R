# Independent rounded-row and projection witness for maintainer review.
# Reuses independent base-R numeric helpers; no live SAS or physical log claim.
# Rounded scalar source/control witness for principal and maintainer review.
# Independent base-R testbed evidence; no live SAS or physical SAS log claim.
limit <- 2147483647
normal <- .Machine$double.xmin
hex <- function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
number_text <- function(x) if(is.na(x)) '.' else sprintf('%.17g',x)
numeric_operand <- function(x) {
  if(is.nan(x)) stop('NaN is not ordinary missing')
  if(is.na(x)) return(NA_real_)
  if(!is.finite(x) || abs(x)>limit || (x!=0 && abs(x)<normal)) stop('numeric bound')
  if(x==0) 0 else x
}
bound <- function(kind,text) {
  if(kind=='missing') return(NA_real_)
  if(kind!='number') stop('ordinary numeric operand required')
  numeric_operand(suppressWarnings(as.numeric(text)))
}
arithmetic <- function(op,a,b) {
  a <- numeric_operand(a);b <- numeric_operand(b)
  if(op=='**' && !is.na(b) && (b!=trunc(b) || b<0 || b>32 || (!is.na(a) && a==0 && b==0))) stop('power domain')
  if(op=='/' && !is.na(b) && b==0) stop('division domain')
  if(is.na(a) || is.na(b)) return(NA_real_)
  q <- switch(op,'+'=a+b,'-'=a-b,'*'=a*b,'/'=a/b,'**'=a^b,stop('operator'))
  if(q==0 && a!=0 && b!=0 && op %in% c('*','/','**')) stop('underflow')
  numeric_operand(q)
}
call <- function(name,values) {
  if(name=='constant') {
    if(length(values)!=1L || !identical(values[[1]],'pi')) stop('constant domain')
    return(pi)
  }
  if(length(values)!=1L) stop('arity')
  x <- numeric_operand(values[[1]])
  if(is.na(x)) return(NA_real_)
  if(name %in% c('sin','cos') && abs(x)>pi) stop('radian domain')
  if(name=='tan' && abs(x)>pi/4) stop('tangent domain')
  if(name %in% c('arsin','arcos') && abs(x)>1) stop('inverse domain')
  value <- switch(name,sin=sin(x),cos=cos(x),tan=tan(x),arsin=asin(x),
                  arcos=acos(x),atan=atan(x),stop('function'))
  numeric_operand(value)
}
logical_number <- function(x) {
  if(is.na(x)) return('.')
  if(!is.finite(x)) stop('output finite')
  if(x==0) return('0')
  if(x==trunc(x)) {
    if(abs(x)>99999999999) stop('output integer magnitude')
    return(sprintf('%.0f',x))
  }
  if(abs(x)<1e-4 || abs(x)>=1e9) stop('output fraction magnitude')
  width <- nchar(sprintf('%.0f',trunc(abs(x))))
  places <- 12L-as.integer(x<0)-width-1L
  fmt <- paste0('%.',places,'f')
  token <- sprintf(fmt,x)
  if(nchar(token)>12L) stop('output carry width')
  # Different host-language rounding with a conservative17ULP stability witness.
  # The implementation's exact rational guard is16ULP; these cases stay clear.
  exponent <- as.numeric(strsplit(sprintf('%a',abs(x)),'p',fixed=TRUE)[[1]][2])
  step <- 2^(exponent-52)
  if(sprintf(fmt,x-17*step)!=token || sprintf(fmt,x+17*step)!=token) stop('decimal midpoint')
  token <- sub('0+$','',token);token <- sub('\\.$','',token)
  if(token=='-0') '0' else token
}
record <- function(values) {
  text <- paste0(paste(vapply(values,logical_number,''),collapse=' '),' ')
  if(nchar(text)>64L) stop('output row width')
  text
}
capture <- function(pattern,text) {
  match <- regmatches(text,regexec(paste0('(?i)^',pattern,'$'),text,perl=TRUE))[[1]]
  if(length(match)) match[-1] else NULL
}
scan_program <- function(path) {
  text <- paste(readLines(path,warn=FALSE),collapse='\n')
  chars <- strsplit(text,'',fixed=TRUE)[[1]]
  at <- 1L;buffer <- '';statements <- character();comment <- FALSE;quote <- ''
  while(at<=length(chars)) {
    ch <- chars[at];after <- if(at<length(chars)) chars[at+1L] else ''
    if(comment) {
      if(ch=='*' && after=='/') {comment <- FALSE;buffer <- paste0(buffer,' ');at <- at+2L} else at <- at+1L
    } else if(nzchar(quote)) {
      buffer <- paste0(buffer,ch);at <- at+1L
      if(ch==quote) {
        if(after==quote) {buffer <- paste0(buffer,after);at <- at+1L} else quote <- ''
      }
    } else if(ch=='/' && after=='*') {comment <- TRUE;at <- at+2L}
    else if(ch %in% c("'",'"')) {quote <- ch;buffer <- paste0(buffer,ch);at <- at+1L}
    else if(ch==';') {
      statement <- trimws(buffer);if(!nzchar(statement)) stop('null source statement')
      statements <- c(statements,statement);buffer <- '';at <- at+1L
    } else {buffer <- paste0(buffer,ch);at <- at+1L}
  }
  if(comment || nzchar(quote) || nzchar(trimws(buffer))) stop('unconsumed source')
  statements
}
parse_expr <- function(text) {
  pattern <- "'[^']*'|\"[^\"]*\"|[0-9]+(?:\\.[0-9]*)?(?:[eE][+-]?[0-9]+)?|\\.[0-9]+(?:[eE][+-]?[0-9]+)?|[a-z_]\\w*|\\*\\*|[.(),+*/-]"
  tokens <- regmatches(tolower(text),gregexpr(pattern,tolower(text),perl=TRUE))[[1]]
  if(!length(tokens) || paste(tokens,collapse='')!=gsub('[[:space:]]','',tolower(text))) stop('expression tokens')
  at <- 1L
  peek <- function() if(at<=length(tokens)) tokens[at] else ''
  take <- function(expected=NULL) {
    if(at>length(tokens)) stop('expression ends early')
    x <- tokens[at];at <<- at+1L
    if(!is.null(expected) && x!=expected) stop('required expression token')
    x
  }
  atom <- function() {
    x <- take()
    if(x=='(') {value <- expression();take(')');return(value)}
    if(x=='.') return(list(kind='number',value=NA_real_))
    if(grepl('^[0-9.]',x)) return(list(kind='number',value=numeric_operand(as.numeric(x))))
    if(substr(x,1,1) %in% c("'",'"')) return(list(kind='string',value=substr(x,2,nchar(x)-1)))
    if(!grepl('^[a-z_]\\w*$',x,perl=TRUE)) stop('primary token')
    if(peek()=='(') {
      take('(');args <- list()
      if(peek()!=')') {
        args[[1]] <- expression()
        while(peek()==',') {take(',');args[[length(args)+1L]] <- expression()}
      }
      take(')');return(list(kind='call',name=x,args=args))
    }
    list(kind='variable',name=x)
  }
  power <- function() {
    if(peek() %in% c('+','-')) {op <- take();return(list(kind='unary',op=op,value=power()))}
    value <- atom()
    if(peek()=='**') {take('**');value <- list(kind='binary',op='**',left=value,right=power())}
    value
  }
  product <- function() {
    value <- power()
    while(peek() %in% c('*','/')) {op <- take();value <- list(kind='binary',op=op,left=value,right=power())}
    value
  }
  expression <- function() {
    value <- product()
    while(peek() %in% c('+','-')) {op <- take();value <- list(kind='binary',op=op,left=value,right=product())}
    value
  }
  value <- expression();if(at<=length(tokens)) stop('unconsumed expression');value
}

ordinary<-function(x) grepl('^[a-z_][a-z0-9_]{0,31}$',x,perl=TRUE) &&
  !(x %in% c('_n_','_error_','_all_','_numeric_','_character_','_temporary_',
             '_infile_','_file_','_ods_','_page_','_blankpage_'))
expand<-function(text) {
  if(any(as.integer(charToRaw(text))>127)) stop('ASCII names')
  text<-tolower(trimws(gsub(' *- *','-',text)))
  tokens<-strsplit(text,' +',perl=TRUE)[[1]];answer<-character()
  for(token in tokens) {
    pair<-strsplit(token,'-',fixed=TRUE)[[1]]
    if(length(pair)==1 && ordinary(token)) answer<-c(answer,token) else {
      if(length(pair)!=2) stop('range')
      suffix<-sub('^.*?([0-9]+)$','\\1',pair,perl=TRUE)
      prefix<-sub('[0-9]+$','',pair)
      if(any(!grepl('^[1-9][0-9]*$',suffix)) || prefix[1]!=prefix[2] ||
         any(nchar(suffix)>2) || any(!vapply(pair,ordinary,FALSE))) stop('range')
      lo<-as.integer(suffix[1]);hi<-as.integer(suffix[2])
      if(lo>hi || lo<1 || hi>64) stop('range bounds')
      answer<-c(answer,paste0(prefix[1],seq.int(lo,hi)))
    }
  }
  if(!length(answer) || length(answer)>64 || anyDuplicated(answer) ||
     any(!vapply(answer,ordinary,FALSE))) stop('list')
  answer
}
select<-function(schema,mode,names) {
  if(is.null(mode)) return(schema)
  if(!(mode %in% c('keep','drop')) || any(!(names %in% schema))) stop('unresolved')
  selected<-schema[(schema %in% names)==(mode=='keep')]
  if(!length(selected)) stop('empty')
  selected
}
selection<-function(text,option=FALSE) {
  pattern<-if(option) '^(keep|drop) *= *(.*)$' else '^(keep|drop) +(.*)$'
  fields<-regmatches(tolower(trimws(text)),regexec(pattern,tolower(trimws(text)),perl=TRUE))[[1]]
  if(length(fields)!=3) stop('selection')
  list(mode=fields[2],names=expand(fields[3]))
}
choose<-function(schema,p) if(is.null(p)) schema else select(schema,p$mode,p$names)
dataset<-function(text,keyword) {
  fields<-regmatches(text,regexec(paste0('^',keyword,' +([a-z_][a-z0-9_]*)(?: *\\((.*)\\))?$'),
                                  text,perl=TRUE))[[1]]
  if(!length(fields)) stop('dataset')
  list(name=fields[2],projection=if(length(fields)>2 && nzchar(fields[3])) selection(fields[3],TRUE) else NULL)
}

load_catalog <- function(folder) {
  descriptors <- read.csv(file.path(folder,'descriptors.csv'),colClasses='character',na.strings=NULL)
  values <- read.csv(file.path(folder,'values.csv'),colClasses='character',na.strings=NULL)
  tables <- list()
  for(i in seq_len(nrow(descriptors))) {
    d <- descriptors[i,];name <- d$table
    if(!(d$type %in% c('number','typed-number','character')) ||
       (d$type %in% c('number','typed-number') && !(d$length %in% c('-','8'))) ||
       (d$type=='character' && (d$length=='-' || as.numeric(d$length)<1 || as.numeric(d$length)>32767))) stop('generic descriptor')
    if(is.null(tables[[name]])) tables[[name]] <- list(schema=list(),rows=list(),encoding=d$encoding,label=d$dataset_label)
    tables[[name]]$schema[[d$name]] <- as.list(d[c('type','length','label','format')])
  }
  for(i in seq_len(nrow(values))) {
    d <- values[i,];table <- tables[[d$table]];position <- as.integer(d$row)
    if(length(table$rows)<position) table$rows[[position]] <- list()
    spec <- table$schema[[d$name]]
    if(d$kind=='missing') value <- NA_real_
    else if(d$kind=='number') {
      value <- as.numeric(d$value)
      if(!is.finite(value)) stop('generic finite input')
    } else if(d$kind=='character' && spec$type=='character') {
      if(nchar(d$value,type='bytes')>as.integer(spec$length)) stop('generic input width')
      value <- paste0(d$value,strrep(' ',as.integer(spec$length)-nchar(d$value,type='bytes')))
    } else stop('generic imported type')
    table$rows[[position]][[d$name]] <- value;tables[[d$table]] <- table
  }
  for(name in names(tables)) {
    table <- tables[[name]]
    for(row in table$rows) if(!setequal(names(row),names(table$schema))) stop('generic row shape')
  }
  tables
}
encode_row <- function(row) paste(vapply(row,function(x) {
  if(is.character(x)) paste0('C',hex(x)) else if(is.na(x)) 'M' else paste0('N',sprintf('%.17g',x))
},''),collapse=',')
number_spec <- function() list(type='number',length='-',label='-',format='-')
program <- function(path,folder) {
  statements <- scan_program(path);at <- 1L;tables <- load_catalog(folder);logs <- character()
  accounts <- list();cat('STATEMENTS:',length(statements),'\n',sep='')
  while(at<=length(statements)) {
    header <- dataset(tolower(statements[at]),'data');at <- at+1L
    name <- header$name;schema <- list();retained <- list();outp <- header$projection
    input <- list(list());input_names <- character();explicit <- FALSE;seen_executable <- FALSE;source_metadata <- list(encoding='-',label='-')
    add_name <- function(n,spec=number_spec()) if(is.null(schema[[n]])) schema[[n]] <<- spec
    constant_expr <- function(expr) {
      if(expr$kind %in% c('number','string')) return(list(known=TRUE,value=expr$value))
      if(expr$kind=='variable') return(list(known=FALSE))
      if(expr$kind=='unary') {
        child <- constant_expr(expr$value)
        return(if(child$known) list(known=TRUE,value=if(expr$op=='-') -child$value else child$value) else list(known=FALSE))
      }
      if(expr$kind=='binary') {
        a <- constant_expr(expr$left);b <- constant_expr(expr$right)
        if(expr$op=='/' && b$known && !is.na(b$value) && b$value==0) stop('static divisor')
        if(expr$op=='**' && b$known && !is.na(b$value) && (b$value!=trunc(b$value) || b$value<0 || b$value>32)) stop('static exponent')
        return(if(a$known && b$known) list(known=TRUE,value=arithmetic(expr$op,a$value,b$value)) else list(known=FALSE))
      }
      if(expr$kind=='call') {
        args <- lapply(expr$args,constant_expr)
        return(if(all(vapply(args,function(x) x$known,FALSE))) list(known=TRUE,value=call(expr$name,lapply(args,function(x) x$value))) else list(known=FALSE))
      }
      stop('static expression')
    }
    discover <- function(expr) {
      constant_expr(expr)
      if(expr$kind=='variable' && expr$name!='_n_') add_name(expr$name)
      if(expr$kind=='binary') {discover(expr$left);discover(expr$right)}
      if(expr$kind=='unary') discover(expr$value)
      if(expr$kind=='call') for(x in expr$args) discover(x)
    }
    parse_op <- function(text,nested=FALSE) {
      if(grepl('^set ',text)) {
        if(nested || length(input_names) || seen_executable) stop('driving input position')
        src <- dataset(text,'set');table <- tables[[src$name]]
        if(is.null(table)) stop('source absent')
        input_names <<- choose(names(table$schema),src$projection)
        for(n in input_names) {
          if(!ordinary(n)) stop('ordinary selected numeric name')
          if(!(table$schema[[n]]$type %in% c('number','typed-number'))) stop('selected numeric descriptor')
          add_name(n,table$schema[[n]])
        }
        input <<- lapply(table$rows,function(row) {
          selected <- row[input_names]
          lapply(selected,numeric_operand)
        })
        source_metadata <<- table[c('encoding','label')]
        return(list(kind='declare'))
      }
      if(grepl('^(keep|drop) ',text)) {
        if(nested || !is.null(outp)) stop('projection context')
        outp <<- selection(text);return(list(kind='declare'))
      }
      retain <- capture('retain\\s+([a-z_]\\w*)\\s+(.+)',text)
      if(!is.null(retain)) {
        if(nested) stop('retain context')
        add_name(retain[1]);initial <- parse_expr(retain[2])
        if(initial$kind!='number') stop('retain initializer')
        retained[[retain[1]]] <<- initial$value
        return(list(kind='declare'))
      }
      seen_executable <<- TRUE
      loop <- capture('do\\s+([a-z_]\\w*)\\s*=\\s*([+-]?[0-9]+)\\s+to\\s+([+-]?[0-9]+)(?:\\s+by\\s+([+-]?[0-9]+))?',text)
      condition <- capture('if\\s+(.+?)\\s+then\\s+(.+)',text)
      subset <- capture('if\\s+(.+)',text)
      put <- capture('put\\s+([a-z_]\\w*(?:\\s+[a-z_]\\w*)*)',text)
      assignment <- capture('([a-z_]\\w*)\\s*=\\s*(.+)',text)
      summation <- capture('([a-z_]\\w*)\\s*\\+\\s*(.+)',text)
      if(!is.null(loop)) {
        add_name(loop[1]);by <- if(nzchar(loop[4])) as.numeric(loop[4]) else 1
        if(by==0) stop('zero loop BY')
        return(list(kind='loop',name=loop[1],start=as.numeric(loop[2]),stop=as.numeric(loop[3]),by=by,body=parse_body(TRUE)))
      }
      if(!is.null(condition) || !is.null(subset)) {
        c <- if(!is.null(condition)) condition else subset
        relation <- capture('(.+?)\\s*(>=|<=|>|<|=|ne)\\s*(.+)',c[1])
        left <- parse_expr(if(is.null(relation)) c[1] else relation[1]);discover(left)
        right <- if(is.null(relation)) NULL else parse_expr(relation[3])
        if(!is.null(right)) discover(right)
        return(list(kind=if(is.null(condition)) 'subset' else 'if',op=if(is.null(relation)) 'truth' else relation[2],left=left,right=right,
          body=if(is.null(condition)) list() else list(parse_op(c[2],nested))))
      }
      if(!is.null(put)) {
        names <- strsplit(put,'\\s+',perl=TRUE)[[1]]
        if(length(input_names) && any(!(names %in% names(schema)))) stop('supplied PUT discovery')
        for(n in names) add_name(n)
        return(list(kind='put',names=names))
      }
      if(text=='output') {explicit <<- TRUE;return(list(kind='output'))}
      if(!is.null(assignment) || !is.null(summation)) {
        match <- if(!is.null(assignment)) assignment else summation
        add_name(match[1]);value <- parse_expr(match[2]);discover(value)
        if(is.null(assignment) && is.null(retained[[match[1]]])) retained[[match[1]]] <<- 0
        return(list(kind=if(is.null(assignment)) 'sum' else 'assign',name=match[1],value=value))
      }
      stop(paste('unsupported statement',text))
    }
    parse_body <- function(nested=FALSE) {
      body <- list()
      repeat {
        if(at>length(statements)) stop('missing terminator')
        text <- tolower(statements[at]);at <<- at+1L
        if(text=='end') {if(!nested) stop('unexpected END');return(body)}
        if(text=='run') {if(nested) stop('RUN inside loop');return(body)}
        body[[length(body)+1L]] <- parse_op(text,nested)
      }
    }
    body <- parse_body();chosen <- choose(names(schema),outp);output <- list();trips <- 0L
    check_put <- function(body) for(op in body) {
      if(op$kind=='put') for(n in op$names) if(schema[[n]]$format!='-') stop('formatted numeric PUT')
      if(op$kind %in% c('loop','if')) check_put(op$body)
    }
    check_put(body)
    row <- list();iteration <- 0L
    evaluate <- function(expr) {
      if(expr$kind %in% c('number','string')) return(expr$value)
      if(expr$kind=='variable') return(if(expr$name=='_n_') iteration else row[[expr$name]])
      if(expr$kind=='unary') return(numeric_operand(if(expr$op=='-') -evaluate(expr$value) else evaluate(expr$value)))
      if(expr$kind=='binary') return(arithmetic(expr$op,evaluate(expr$left),evaluate(expr$right)))
      if(expr$kind=='call') return(call(expr$name,lapply(expr$args,evaluate)))
      stop('unsupported expression')
    }
    test <- function(op) {
      a <- evaluate(op$left)
      if(op$op=='truth') return(!is.na(a) && a!=0)
      b <- evaluate(op$right)
      if(is.na(a) || is.na(b)) {
        if(is.na(a) && is.na(b)) {a <- 0;b <- 0}
        else {a <- if(is.na(a)) -Inf else a;b <- if(is.na(b)) -Inf else b}
      }
      switch(op$op,'>'=a>b,'<'=a<b,'>='=a>=b,'<='=a<=b,'='=a==b,ne=a!=b)
    }
    perform <- function(body) {
      for(op in body) {
        if(op$kind=='declare') next
        if(op$kind=='assign') row[[op$name]] <<- evaluate(op$value)
        else if(op$kind=='sum') {
          x <- evaluate(op$value);old <- row[[op$name]]
          row[[op$name]] <<- arithmetic('+',if(is.na(old)) 0 else old,if(is.na(x)) 0 else x)
        } else if(op$kind=='output') output[[length(output)+1L]] <<- row[chosen]
        else if(op$kind=='put') logs <<- c(logs,record(row[op$names]))
        else if(op$kind=='subset') {if(!test(op)) return(FALSE)}
        else if(op$kind=='if') {if(test(op) && !perform(op$body)) return(FALSE)}
        else if(op$kind=='loop') {
          row[[op$name]] <<- op$start
          while(if(op$by>0) row[[op$name]]<=op$stop else row[[op$name]]>=op$stop) {
            trips <<- trips+1L;if(trips>10000L*max(1,iteration)) stop('loop budget')
            if(!perform(op$body)) return(FALSE)
            row[[op$name]] <<- arithmetic('+',row[[op$name]],op$by)
          }
        } else stop('unsupported execution')
      }
      TRUE
    }
    for(inrow in input) {
      iteration <- iteration+1L
      row <- setNames(as.list(rep(NA_real_,length(schema))),names(schema))
      row[names(retained)] <- retained
      row[names(inrow)] <- inrow
      completed <- perform(body)
      retained <- row[unique(c(input_names,names(retained)))]
      if(completed && !explicit) output[[length(output)+1L]] <- row[chosen]
    }
    table <- list(schema=schema[chosen],rows=output,encoding=source_metadata$encoding,label=source_metadata$label)
    if(name!='_null_') tables[[name]] <- table
    accounts[[length(accounts)+1L]] <- list(name=name,iterations=length(input),trips=trips)
  }
  for(n in names(tables)) {
    table <- tables[[n]];cat('TABLE:',n,'\n','META:',table$encoding,'|',table$label,'\n',sep='')
    for(nm in names(table$schema)) {
      spec <- table$schema[[nm]]
      cat('COLUMN:',paste(c(nm,spec$type,spec$length,spec$label,spec$format),collapse='|'),'\n',sep='')
    }
    for(row in table$rows) cat('ROW:',encode_row(row[names(table$schema)]),'\n',sep='')
  }
  for(account in accounts) cat('ACCOUNT:',account$name,',',account$iterations,',',account$trips,'\n',sep='')
  for(log in logs) cat('LOG:',hex(log),'\n',sep='')
}
args <- commandArgs(trailingOnly=TRUE)
if(length(args)==3L && args[1]=='program') {program(args[2],args[3])} else if(length(args)==2L && args[1]=='batch') {
  cases <- read.csv(file.path(args[2],'cases.csv'),colClasses='character')
  for(i in seq_len(nrow(cases))) {
    cat('CASE:',i-1L,'\n',sep='')
    passed <- tryCatch({program(file.path(args[2],cases$source[i]),file.path(args[2],cases$catalog[i]));TRUE},error=function(e) FALSE)
    cat('ANSWER:',if(passed) 'OK' else 'REFUSE','\n',sep='')
  }
} else stop('program path catalog-folder or batch folder required')

